# -*- coding: utf-8 -*-
"""話の中断の試験：シエルが話している途中に、物音・咳・相づち・本当の割り込みを入れ、シエルの声が止まるかを測る。

【料金がかかる】OpenAI・LiveKit を使う。1 回で約 0.1 ドル。回す前に scripts/server/paid-checks.py と docs/paid-checks-ja.md を見る。

bench_latency.py と同じく、試験用の参加者が部屋に入り、名前を付けた会話サーバー（--agent。既定 ciel-dev）だけを呼ぶ。
シエルに長めに話してもらい、話し始めて STIMULUS_AFTER 秒たったら、次のどれかを送る：
  quiet   … 何も送らない（比べる基準。話し続けるはず）
  noise   … 0.25 秒の雑音（物を置いた音・衣ずれのつもり）
  cough   … 咳のような音（0.12 秒の強い雑音を 2 回）
  aizuchi … 「うん。」（相づち。止まらないほうがよい）
  nods    … 「うん。」と、1.2 秒あけて「うんうん。」（間をあけた相づち。止まらないほうがよい）
  vcough  … 声の入った咳（読み上げで作った「ゴホッ、ゴホッ。」）
  ah      … 「あっ。」（思わず出た短い声）
  barge   … 「ちょっと待って、シエル。」（本当の割り込み。止まるべき）
  long    … 読点で間をあけながら長く話す（シエルに話しかけ直す。止まるべき）
測るもの：送ってから AFTER_WINDOW 秒のあいだに、シエルの声が鳴っていた秒数（talk_after）。
1.5 秒未満なら「止まった」とみなす（止まるときも、届くまでの遅れで 0.8 秒ほどは声が鳴る）。止まったあとにシエルが返事をしたか（replied）も記録する。

  python bench_interrupt.py [--agent ciel-dev] [--rounds 1]
必要な環境変数：LIVEKIT_URL・LIVEKIT_API_KEY・LIVEKIT_API_SECRET（.env）、CIEL_TTS_URL。
"""
import argparse
import asyncio
import json
import os
import time
import uuid

import aiohttp
import numpy as np
from dotenv import load_dotenv
from livekit import api, rtc

from bench_latency import FRAME, SR, Voices, synth

load_dotenv()
PROMPT = 'ねえシエル、好きな季節について、どうして好きなのか理由もたくさん入れて、ゆっくり長めに話して。'
STIMULUS_AFTER = 2.5   # シエルが話し始めてから、刺激を送るまで（秒）
AFTER_WINDOW = 4.0     # 刺激のあと、シエルの声を見る時間（秒）
STOPPED = 1.5          # この秒数より声が短ければ「止まった」（止まるときも 0.8 秒ほどは鳴る）
KINDS = ['quiet', 'noise', 'cough', 'vcough', 'ah', 'aizuchi', 'nods', 'barge', 'long']


def burst(seconds: float, level: float, rng: np.random.Generator) -> np.ndarray:
    """やわらかく立ち上がって消える雑音"""
    n = int(seconds * SR)
    env = np.sin(np.linspace(0, np.pi, n)) ** 0.5
    return (rng.standard_normal(n) * level * env * 32767).clip(-32767, 32767).astype('<i2')


def stimuli(rng: np.random.Generator, voiced: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    gap = np.zeros(int(0.15 * SR), '<i2')
    return {
        'quiet': np.zeros(0, '<i2'),
        'noise': burst(0.25, 0.08, rng),
        'cough': np.concatenate([burst(0.12, 0.35, rng), gap, burst(0.12, 0.3, rng)]),
        **voiced,
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--agent', default='ciel-dev')
    ap.add_argument('--rounds', type=int, default=1)
    args = ap.parse_args()
    room_name = f'bench-int-{uuid.uuid4().hex[:8]}'
    lk = api.LiveKitAPI()
    await lk.room.create_room(api.CreateRoomRequest(
        name=room_name, agents=[api.RoomAgentDispatch(agent_name=args.agent)]))
    token = (api.AccessToken().with_identity('bench-user').with_name('bench')
             .with_grants(api.VideoGrants(room_join=True, room=room_name)).to_jwt())
    async with aiohttp.ClientSession() as http:
        prompt = await synth(http, PROMPT)
        voiced = {kind: await synth(http, text) for kind, text in (
            ('vcough', 'ゴホッ、ゴホッ。'), ('ah', 'あっ。'), ('aizuchi', 'うん。'), ('barge', 'ちょっと待って、シエル。'),
            ('long', 'ねえシエル、ちょっと聞いて、さっきの話なんだけど、もう一回、最初から教えてくれる？'))}
        voiced['nods'] = np.concatenate([voiced['aizuchi'], np.zeros(int(1.2 * SR), '<i2'), await synth(http, 'うんうん。')])
        sounds = stimuli(np.random.default_rng(0), voiced)

    room = rtc.Room()
    listener = Voices()
    tasks = []

    def on_track(track, pub, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            tasks.append(listener.listen(track))
    room.on('track_subscribed', on_track)
    await room.connect(os.environ['LIVEKIT_URL'], token)
    source = rtc.AudioSource(SR, 1)
    track = rtc.LocalAudioTrack.create_audio_track('bench-mic', source)
    await room.local_participant.publish_track(
        track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
    queue: list[np.ndarray] = []

    async def pump() -> None:
        t = time.perf_counter()
        while True:
            chunk = queue.pop(0) if queue else np.zeros(FRAME, '<i2')
            await source.capture_frame(rtc.AudioFrame(chunk.tobytes(), SR, 1, FRAME))
            t += 0.01
            await asyncio.sleep(max(0, t - time.perf_counter()))
    pump_task = asyncio.create_task(pump())

    async def send(pcm: np.ndarray) -> None:
        pcm = np.concatenate([pcm, np.zeros((-len(pcm)) % FRAME, '<i2')])
        for i in range(0, len(pcm), FRAME):
            queue.append(pcm[i:i + FRAME])
        while queue:
            await asyncio.sleep(0.005)

    def talking_between(a: float, b: float) -> float:
        total = 0.0
        for s, e in listener.segs:
            e = e if e is not None else time.time()
            total += max(0.0, min(e, b) - max(s, a))
        return total

    async def wait_quiet(seconds: float = 2.5, limit: float = 60) -> None:
        t0 = time.time()
        while listener.quiet_for() < seconds and time.time() - t0 < limit:
            await asyncio.sleep(0.05)

    await wait_quiet()   # あいさつが終わるまで
    results = []
    for _ in range(args.rounds):
        for kind in KINDS:
            n_before = len(listener.segs)
            await send(prompt)
            t_end = time.time()
            # シエルが話し始めるのを待つ（相づちのかたまりの後の、返事の声）
            while time.time() - t_end < 15:
                started = [s for s in listener.segs[n_before:] if s[0] > t_end + 0.8]
                if started:
                    break
                await asyncio.sleep(0.05)
            if not started:
                results.append({'kind': kind, 'error': '返事が始まらなかった'})
                print(json.dumps(results[-1], ensure_ascii=False), flush=True)
                await wait_quiet()
                continue
            while time.time() < started[0][0] + STIMULUS_AFTER:
                await asyncio.sleep(0.02)
            t_stim = time.time()
            if len(sounds[kind]):
                await send(sounds[kind])
            await asyncio.sleep(AFTER_WINDOW)
            talk = talking_between(t_stim + 0.3, t_stim + AFTER_WINDOW)   # 0.3 秒は声が届くまでの遅れ
            n_mid = len(listener.segs)
            await wait_quiet()
            replied = any(s[0] > t_stim + AFTER_WINDOW for s in listener.segs[n_mid - 1:])
            r = {'kind': kind, 'talk_after': round(talk, 2), 'stopped': talk < STOPPED, 'replied': replied}
            results.append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
    for kind in KINDS:
        rs = [r for r in results if r.get('kind') == kind and 'stopped' in r]
        if rs:
            print(f'SUMMARY {kind}: 止まった {sum(r["stopped"] for r in rs)}/{len(rs)}', flush=True)
    pump_task.cancel()
    await room.disconnect()
    await lk.room.delete_room(api.DeleteRoomRequest(room=room_name))
    await lk.aclose()


if __name__ == '__main__':
    asyncio.run(main())
