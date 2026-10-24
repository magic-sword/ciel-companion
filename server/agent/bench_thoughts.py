# -*- coding: utf-8 -*-
"""内なる考えの試験：おしゃべりにして少し話し、黙ったあと、シエルがいつ自分から話しかけるかを見る（initiative.py）。

【料金がかかる】OpenAI・LiveKit を使う。1 回で約 0.1〜0.3 ドル（会話モデル数回と、考える係。黙る時間が長いほど考える係が増える）。回す前に scripts/server/paid-checks.py と docs/paid-checks-ja.md を見る。

bench_latency.py と同じく、試験用の参加者が部屋に入り、名前を付けた会話サーバー（--agent。既定 ciel-dev）だけを呼ぶ。
アプリと同じ知らせ（ciel.style）で、おしゃべり度を「おしゃべり」にする。LINES を 1 つずつ話して返事を待ち、
そのあと --silence 秒黙って、シエルの声（相づちを除く）が始まった時刻を記録する。
考えの中身と話しかけた言葉は、開発用のデバッグログ（thoughts・thought_expressed・item）で見る。

  python bench_thoughts.py [--agent ciel-dev] [--silence 150] [--ask]
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

from bench_latency import FRAME, SR, Listener, synth

load_dotenv()
LINES = ['ねえシエル、昨日の夜、冬の星空を撮りに山の方まで行ってきたんだ。',
         'オリオン座がすごくきれいに撮れたよ。でも寒くて手がかじかんじゃった。',
         '今度は流れ星も撮ってみたいんだよね。']
ASK = 'シエル、今なに考えてたの？'   # --ask：最後に心の中を聞く（道具 read_inner_thoughts を使うか）
QUIET = 2.5


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--agent', default='ciel-dev')
    ap.add_argument('--silence', type=float, default=150)
    ap.add_argument('--ask', action='store_true')
    args = ap.parse_args()
    room_name = f'bench-{uuid.uuid4().hex[:8]}'
    lk = api.LiveKitAPI()
    await lk.room.create_room(api.CreateRoomRequest(
        name=room_name, agents=[api.RoomAgentDispatch(agent_name=args.agent)]))
    token = (api.AccessToken().with_identity('bench-user').with_name('bench')
             .with_grants(api.VideoGrants(room_join=True, room=room_name)).to_jwt())
    async with aiohttp.ClientSession() as http:
        pcm = {t: await synth(http, t) for t in [*LINES, ASK]}

    room = rtc.Room()
    voice, aizuchi = Listener(), Listener()
    tasks = []

    def on_track(track, pub, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            target = aizuchi if 'aizuchi' in (pub.name or '') else voice
            tasks.append(asyncio.create_task(target.run(track)))
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

    async def say(text: str) -> None:
        print(f"{time.strftime('%H:%M:%S')} 話す：{text}", flush=True)
        x = pcm[text]
        x = np.concatenate([x, np.zeros((-len(x)) % FRAME, '<i2')])
        for i in range(0, len(x), FRAME):
            queue.append(x[i:i + FRAME])
        while queue:
            await asyncio.sleep(0.005)

    async def wait_quiet(limit: float = 40) -> None:
        t0 = time.time()
        await asyncio.sleep(1.0)
        while min(voice.quiet_for(), aizuchi.quiet_for()) < QUIET and time.time() - t0 < limit:
            await asyncio.sleep(0.05)

    await asyncio.sleep(3)
    await wait_quiet()   # あいさつ
    style = {'v': 1, 'type': 'conversation.style', 'talk': 'chatty', 'presence': 'close', 'meeting': False}
    await room.local_participant.publish_data(json.dumps(style), reliable=True, topic='ciel.style')
    for line in LINES:
        await say(line)
        await asyncio.sleep(1.0)
        await wait_quiet()
    quiet_from = time.time()
    print(f"{time.strftime('%H:%M:%S')} {args.silence:.0f} 秒黙る", flush=True)
    await asyncio.sleep(args.silence)
    starts = [round(a - quiet_from, 1) for a, _ in voice.segs if a > quiet_from + 0.5]
    # 声のかたまりは文ごとに分かれるので、5 秒以上あいたものを 1 回の話しかけとして数える
    talks = [s for i, s in enumerate(starts) if i == 0 or s - starts[i - 1] > 5]
    print(f'SUMMARY 黙ってから話しかけた時刻（秒）：{talks}  部屋：{room_name}', flush=True)
    if args.ask:
        await wait_quiet()
        await say(ASK)
        await asyncio.sleep(1.0)
        await wait_quiet(60)
    pump_task.cancel()
    await room.disconnect()
    await lk.room.delete_room(api.DeleteRoomRequest(room=room_name))
    await lk.aclose()


if __name__ == '__main__':
    asyncio.run(main())
