# -*- coding: utf-8 -*-
"""返事の速さを測る：試験用の参加者が、合成した声で話しかけ、話し終わりからシエルの声が届くまでを測る。

本番の会話サーバーは入らない部屋を作り、agent_name を付けた試験用の会話サーバー（CIEL_AGENT_NAME）だけを呼ぶ。
声は読み上げサービス（Irodori-TTS）で、シエルとは違う声（大人の男性）で作る。

  python bench_latency.py [--agent ciel-bench] [--rounds 1]

測るもの（発言ごと）：
  first … 話し終わり（声の最後のフレームを送った時刻）から、シエルの声（相づちを含む）が始まるまで
  segs  … シエルの声のかたまり（話し終わりからの始まりと終わりの秒。相づちのトラックの分も入る）
  nods  … 話している途中に始まったシエルの声（話の途中の相づち。話し終わりからの秒なので負になる）
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

load_dotenv()
TTS_URL = os.environ.get('CIEL_TTS_URL', 'http://127.0.0.1:8766/synthesize')
CAPTION = '落ち着いた低めの声の30代の男性。ふつうの速さで、親しい相手に話しかける自然な話し方。'
SR = 48000
FRAME = SR // 100   # 10 ms
LINES = [
    'ねえシエル、今日ちょっと散歩してきたんだけど、すごく気持ちよかったよ。',
    'おはよう。',
    '最近おすすめの本とかある？',
    'えっとね、明日の予定なんだけど、午前中に買い物に行って、午後は家で映画を見ようと思ってるんだ。',
    'うん。',
    'シエルは何色が好き？',
    # 途中で息つぎをしながら長く話す（話している途中の相づちを見る。部分のあいだに PAUSE_SECONDS の無音）
    ['今日はね、朝から散歩に出かけたんだけど', '公園の桜がすごくきれいで', 'それで写真をたくさん撮ってきたんだ。'],
]
PAUSE_SECONDS = 0.6
ON = 0.01        # シエルの声とみなす大きさ（RMS、最大 1）
OFF_SECONDS = 0.4   # これだけ静かなら、声のかたまりの終わり
QUIET_SECONDS = 2.5  # シエルがこれだけ静かなら、話し終えたとみなして次を話す


async def synth(http: aiohttp.ClientSession, text: str) -> np.ndarray:
    async with http.post(TTS_URL, json={'text': text, 'caption': CAPTION}) as r:
        r.raise_for_status()
        sr = int(r.headers.get('X-Sample-Rate', SR))
        pcm = np.frombuffer(await r.read(), '<i2')
    if sr != SR:
        idx = np.arange(0, len(pcm), sr / SR)
        pcm = np.interp(idx, np.arange(len(pcm)), pcm).astype('<i2')
    return pcm


class Listener:
    """シエルの声の始まりと終わりを記録する"""

    def __init__(self) -> None:
        self.segs: list[tuple[float, float | None]] = []
        self._last_loud = 0.0

    async def run(self, track: rtc.Track) -> None:
        try:
            await self._run(track)
        except Exception as e:
            print('シエルの声を受け取れない:', repr(e), flush=True)

    async def _run(self, track: rtc.Track) -> None:
        async for ev in rtc.AudioStream(track, sample_rate=SR, num_channels=1):
            f = ev.frame
            x = np.frombuffer(f.data, '<i2').astype(np.float32) / 32768
            now = time.time()
            if np.sqrt((x ** 2).mean()) > ON:
                if not self.segs or self.segs[-1][1] is not None:
                    self.segs.append((now, None))
                self._last_loud = now
            elif self.segs and self.segs[-1][1] is None and now - self._last_loud > OFF_SECONDS:
                self.segs[-1] = (self.segs[-1][0], self._last_loud)

    def quiet_for(self) -> float:
        if self.segs and self.segs[-1][1] is None:
            return 0.0
        return time.time() - self._last_loud if self._last_loud else 1e9


class Voices:
    """シエルの声のトラックと相づちのトラック（aizuchi.py）をまとめて見る"""

    def __init__(self) -> None:
        self.tracks: dict[str, Listener] = {}

    def listen(self, track: rtc.Track) -> asyncio.Task:
        self.tracks[track.sid] = listener = Listener()
        return asyncio.create_task(listener.run(track))

    @property
    def segs(self) -> list[tuple[float, float | None]]:
        return sorted(s for listener in self.tracks.values() for s in listener.segs)

    def quiet_for(self) -> float:
        return min((listener.quiet_for() for listener in self.tracks.values()), default=1e9)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--agent', default='ciel-bench')
    ap.add_argument('--rounds', type=int, default=1)
    args = ap.parse_args()
    room_name = f'bench-{uuid.uuid4().hex[:8]}'
    lk = api.LiveKitAPI()
    await lk.room.create_room(api.CreateRoomRequest(
        name=room_name, agents=[api.RoomAgentDispatch(agent_name=args.agent)]))
    token = (api.AccessToken().with_identity('bench-user').with_name('bench')
             .with_grants(api.VideoGrants(room_join=True, room=room_name)).to_jwt())

    async with aiohttp.ClientSession() as http:
        voices = []
        for line in LINES:
            parts = [line] if isinstance(line, str) else line
            gap = np.zeros(int(PAUSE_SECONDS * SR), '<i2')
            pcms = [await synth(http, t) for t in parts]
            voices.append(np.concatenate([x for p in pcms for x in (p, gap)][:-1]))
    room = rtc.Room()
    listener = Voices()
    tasks = []

    def on_track(track, pub, participant):
        print(f"{time.strftime('%H:%M:%S')} 受信 {participant.identity} {pub.name}", flush=True)
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            tasks.append(listener.listen(track))
    room.on('track_subscribed', on_track)
    await room.connect(os.environ['LIVEKIT_URL'], token)
    source = rtc.AudioSource(SR, 1)
    track = rtc.LocalAudioTrack.create_audio_track('bench-mic', source)
    await room.local_participant.publish_track(
        track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))

    # 声が途切れないよう、話していないあいだも小さな雑音を送り続ける
    queue: list[np.ndarray] = []
    rng = np.random.default_rng(0)

    async def pump() -> None:
        t = time.perf_counter()
        while True:
            chunk = queue.pop(0) if queue else np.zeros(FRAME, "<i2")
            await source.capture_frame(rtc.AudioFrame(chunk.tobytes(), SR, 1, FRAME))
            t += 0.01
            await asyncio.sleep(max(0, t - time.perf_counter()))
    pump_task = asyncio.create_task(pump())

    async def wait_reply(n_before: int, limit: float = 20) -> None:
        """シエルが話し始め（limit 秒まで待つ）、話し終えて QUIET_SECONDS 静かになるまで待つ。
        話している途中の相づち（t0 より前に始まった声）は数えない"""
        t0 = time.time()
        while not [x for x in listener.segs[n_before:] if x[0] > t0 - 0.1] and time.time() - t0 < limit:
            await asyncio.sleep(0.05)
        while listener.quiet_for() < QUIET_SECONDS and time.time() - t0 < limit + 40:
            await asyncio.sleep(0.05)

    await wait_reply(0)   # あいさつが終わるまで
    results = []
    for _ in range(args.rounds):
        for line, pcm in zip(LINES, voices):
            text = line if isinstance(line, str) else '…'.join(line)
            n_before = len(listener.segs)
            t_start = time.time()
            print(f"{time.strftime('%H:%M:%S')} 話す：{text}", flush=True)
            pad = (-len(pcm)) % FRAME
            pcm = np.concatenate([pcm, np.zeros(pad, '<i2')])
            for i in range(0, len(pcm), FRAME):
                queue.append(pcm[i:i + FRAME])
            while queue:
                await asyncio.sleep(0.005)
            t_end = time.time()
            await wait_reply(n_before)
            nods = [s for s in listener.segs[n_before:] if t_start < s[0] <= t_end - 0.1]
            segs = [s for s in listener.segs[n_before:] if s[0] > t_end - 0.1]
            first = segs[0][0] - t_end if segs else None
            r = {'text': text, 'first': None if first is None else round(first, 2),
                 'nods': [round(a - t_end, 2) for a, _ in nods],
                 'segs': [[round(a - t_end, 2), round((b or a) - t_end, 2)] for a, b in segs]}
            results.append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
    firsts = [r['first'] for r in results if r['first'] is not None]
    if firsts:
        print(f'SUMMARY first: median {np.median(firsts):.2f}s  min {min(firsts):.2f}s  max {max(firsts):.2f}s  '
              f'(n={len(firsts)}/{len(results)})', flush=True)
    pump_task.cancel()
    await room.disconnect()
    await lk.room.delete_room(api.DeleteRoomRequest(room=room_name))
    await lk.aclose()


if __name__ == '__main__':
    asyncio.run(main())
