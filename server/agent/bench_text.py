# -*- coding: utf-8 -*-
"""返事の速さを文字の台本で測る：同じ部屋で決まった発言を文字（lk.chat）で送り、シエルの返事の声が届くまでを測る。

音声で話しかける bench_latency.py は、音声認識の区切り方で返事が作り直され、回ごとに揺れが大きい。ここでは発言を文字で
送り、推論・キャッシュの違いだけを比べる。家の中の LiveKit（docs/operations/local-livekit-ja.md）の試験用の会話サーバーで使う。

  python bench_text.py [--agent ciel-dev] [--rounds 2] [--lines 台本.txt] [--pause 秒]
  --lines は 1 行 1 発言の台本（既定は LINES）。--pause は、返事を話し終えてから次の発言までの間（静かな間に動く処理を見るとき）。

測るもの（発言ごと）：送ってから、シエルの返事の声が始まるまでの秒（first）と、話し終えるまで（done）。
推論の最初の文字までの時間とキャッシュは、その部屋の開発ログを scripts/server/conversation_latency_report.py で読む。
必要な環境変数：LIVEKIT_URL・LIVEKIT_API_KEY・LIVEKIT_API_SECRET。
文字で送った発言は、会話の記録（conversation.py。声の文字起こしの確定で書く）に本文が入らない。記録を読む処理（心の見極め・
今のまとめ・メモ）を確かめるときは、合成した声で話しかける bench_latency.py を使う。
"""
import argparse
import asyncio
import json
import os
import time
import uuid

import numpy as np
from livekit import api, rtc

LINES = [
    'ねえシエル、今日ちょっと散歩してきたんだけど、すごく気持ちよかったよ。',
    'おはよう。',
    '最近おすすめの本とかある？',
    'えっとね、明日の予定なんだけど、午前中に買い物に行って、午後は家で映画を見ようと思ってるんだ。',
    'うん。',
    'シエルは何色が好き？',
    '今日はね、朝から散歩に出かけたんだけど、公園の桜がすごくきれいで、それで写真をたくさん撮ってきたんだ。',
]
SR = 48000
ON = 0.01             # シエルの声とみなす大きさ（RMS、最大 1）
QUIET_SECONDS = 2.5   # シエルがこれだけ静かなら、話し終えたとみなす
LIMIT_SECONDS = 60.0  # 1 つの発言で待つ上限


class Voice:
    """シエルの声（相づちのトラックは除く）の始まりと最後に聞こえた時刻"""

    def __init__(self) -> None:
        self.started: list[float] = []
        self.last = 0.0
        self._loud = False

    async def run(self, track: rtc.Track) -> None:
        async for ev in rtc.AudioStream(track, sample_rate=SR, num_channels=1):
            x = np.frombuffer(ev.frame.data, '<i2').astype(np.float32) / 32768
            now = time.time()
            if np.sqrt((x ** 2).mean()) > ON:
                if now - self.last > QUIET_SECONDS:
                    self.started.append(now)
                self.last = now


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--agent', default='ciel-dev')
    ap.add_argument('--rounds', type=int, default=2)
    ap.add_argument('--lines', help='1 行 1 発言の台本（UTF-8）')
    ap.add_argument('--pause', type=float, default=0.0, help='返事を話し終えてから次の発言までの秒')
    args = ap.parse_args()
    lines = ([x.strip() for x in open(args.lines, encoding='utf-8') if x.strip()] if args.lines else LINES)
    room_name = f'bench-text-{uuid.uuid4().hex[:8]}'
    lk = api.LiveKitAPI()
    await lk.room.create_room(api.CreateRoomRequest(name=room_name, agents=[api.RoomAgentDispatch(agent_name=args.agent)]))
    token = (api.AccessToken().with_identity('bench-user').with_name('bench')
             .with_grants(api.VideoGrants(room_join=True, room=room_name)).to_jwt())
    room = rtc.Room()
    voice = Voice()
    tasks = []

    @room.on('track_subscribed')
    def on_track(track, publication, participant):
        # 相づち（aizuchi.py）は別のトラック。返事の声のトラックだけを聞く
        if track.kind == rtc.TrackKind.KIND_AUDIO and 'aizuchi' not in (publication.name or ''):
            tasks.append(asyncio.create_task(voice.run(track)))

    await room.connect(os.environ['LIVEKIT_URL'], token)

    async def wait_reply(sent: float) -> tuple[float | None, float | None]:
        while time.time() - sent < LIMIT_SECONDS:
            begun = [t for t in voice.started if t >= sent]
            if begun and time.time() - voice.last >= QUIET_SECONDS:
                return begun[0] - sent, voice.last - sent
            await asyncio.sleep(0.05)
        begun = [t for t in voice.started if t >= sent]
        return (begun[0] - sent if begun else None), None

    await wait_reply(time.time())   # あいさつが終わるまで
    results = []
    for _ in range(args.rounds):
        for line in lines:
            sent = time.time()
            await room.local_participant.send_text(line, topic='lk.chat')
            first, done = await wait_reply(sent)
            r = {'text': line, 'first': None if first is None else round(first, 2), 'done': None if done is None else round(done, 2)}
            results.append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
            if args.pause > 0:
                await asyncio.sleep(args.pause)
    firsts = [r['first'] for r in results if r['first'] is not None]
    if firsts:
        print(f'SUMMARY first: median {np.median(firsts):.2f}s  p90 {np.percentile(firsts, 90):.2f}s  max {max(firsts):.2f}s  '
              f'(n={len(firsts)}/{len(results)}) room={room_name}', flush=True)
    for t in tasks:
        t.cancel()
    await room.disconnect()
    await lk.room.delete_room(api.DeleteRoomRequest(room=room_name))
    await lk.aclose()


if __name__ == '__main__':
    asyncio.run(main())
