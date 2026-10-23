# -*- coding: utf-8 -*-
"""返事が止まる件の再現：議事録をとりながら、返事の依頼が重なる話し方と、シエルが話している途中の声を入れ、
そのあとの発言にシエルが返事をするかを確かめる（2026-10-23、本番で議事録をとり始めて約 50 秒後から返事が止まった）。

bench_latency.py と同じく、試験用の参加者が部屋に入り、名前を付けた会話サーバー（--agent。既定 ciel-dev）だけを呼ぶ。
1 回分の流れ（--rounds 回くり返す）：
  double … 話して、返事の声が出る前に続けて話す（返事の依頼が 2 回重なる）
  overlap … 返事の声が出始めて OVERLAP_AFTER 秒で、短く話す（シエルが話している途中の声）
  probe … 静かになってから、ふつうに話しかける。PROBE_LIMIT 秒のうちにシエルの声（相づちを除く）が出なければ「止まった」
最初に「議事録とって」と頼む（--no-minutes で頼まない）。会話サーバーの中の様子は、開発用のデバッグログで追う。

  python bench_stall.py [--agent ciel-dev] [--rounds 4] [--no-minutes]
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
START = 'シエル、今から会議をするから、議事録とってくれる？'
DOUBLE = [('来月の展示の準備なんだけど、テーマは冬の星空にしようと思ってる。', 'あ、あと予算は三万円くらいで考えてる。'),
          ('会場には写真の大きさを問い合わせないといけないね。', 'それと、ポスターは来週の水曜までに作るよ。'),
          ('解説は印刷するか画面で見せるか、まだ決めてないんだ。', 'シエルはどっちがいいと思う？'),
          ('子ども向けの解説も置きたいと思ってるんだよね。', 'わかりやすい言葉で書けるかな。')]
OVERLAP = ['うんうん、なるほどね。', 'へえ、そうなんだ。', 'あ、そっか。', 'うん、いいね。']
PROBE = ['ねえシエル、ここまでの話で決まったことを教えて。', 'シエル、聞こえてる？', 'ところで、今日の天気はどうだった？',
         'シエル、次は何を決めたらいいと思う？']
DOUBLE_GAP = 1.0      # 1 つめを話し終えてから 2 つめを話し始めるまで（秒）。返事の声が出る前に重ねる
OVERLAP_AFTER = 1.0   # 返事の声が出始めてから、途中の声を入れるまで（秒）
PROBE_LIMIT = 15.0    # ふつうの話しかけに、これだけ待って声が出なければ「止まった」
QUIET = 2.5


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--agent', default='ciel-dev')
    ap.add_argument('--rounds', type=int, default=4)
    ap.add_argument('--no-minutes', action='store_true')
    args = ap.parse_args()
    room_name = f'bench-{uuid.uuid4().hex[:8]}'
    lk = api.LiveKitAPI()
    await lk.room.create_room(api.CreateRoomRequest(
        name=room_name, agents=[api.RoomAgentDispatch(agent_name=args.agent)]))
    token = (api.AccessToken().with_identity('bench-user').with_name('bench')
             .with_grants(api.VideoGrants(room_join=True, room=room_name)).to_jwt())
    texts = [START] + [t for pair in DOUBLE for t in pair] + OVERLAP + PROBE
    async with aiohttp.ClientSession() as http:
        pcm = {t: await synth(http, t) for t in texts}

    room = rtc.Room()
    voice, aizuchi = Listener(), Listener()   # シエルの声（返事）と相づちのトラックを分けて見る
    tasks, thinking, summaries = [], [], []

    def on_data(packet) -> None:
        if packet.topic == 'ciel.summary':
            summaries.append(time.time())
            return
        if packet.topic != 'ciel.event':
            return
        try:
            msg = json.loads(packet.data.decode('utf-8'))
        except ValueError:
            return
        if msg.get('type') == 'agent.thinking' and msg.get('on'):
            thinking.append(time.time())
    room.on('data_received', on_data)

    def on_track(track, pub, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            target = aizuchi if 'aizuchi' in (pub.name or '') else voice
            print(f"{time.strftime('%H:%M:%S')} 受信 {pub.name} → {'相づち' if target is aizuchi else '声'}", flush=True)
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

    async def say(text: str) -> float:
        print(f"{time.strftime('%H:%M:%S')} 話す：{text}", flush=True)
        x = pcm[text]
        x = np.concatenate([x, np.zeros((-len(x)) % FRAME, '<i2')])
        for i in range(0, len(x), FRAME):
            queue.append(x[i:i + FRAME])
        while queue:
            await asyncio.sleep(0.005)
        return time.time()

    async def voice_after(t0: float, limit: float) -> float | None:
        """t0 より後にシエルの声（返事）が始まった時刻。limit 秒待っても無ければ None"""
        while time.time() - t0 < limit:
            starts = [a for a, _ in voice.segs if a > t0]
            if starts:
                return starts[0]
            await asyncio.sleep(0.05)
        return None

    async def wait_quiet(limit: float = 40) -> None:
        t0 = time.time()
        while min(voice.quiet_for(), aizuchi.quiet_for()) < QUIET and time.time() - t0 < limit:
            await asyncio.sleep(0.05)

    await voice_after(0, 20)
    await wait_quiet()   # あいさつが終わるまで
    if not args.no_minutes:
        end = await say(START)
        print('議事録を頼んだ返事', 'あり' if await voice_after(end, PROBE_LIMIT) else 'なし', flush=True)
        await wait_quiet()
    results = []
    for i in range(args.rounds):
        first, second = DOUBLE[i % len(DOUBLE)]
        await say(first)
        await asyncio.sleep(DOUBLE_GAP)
        end = await say(second)
        started = await voice_after(end, PROBE_LIMIT)
        if started is not None:
            await asyncio.sleep(max(0.0, started + OVERLAP_AFTER - time.time()))
            await say(OVERLAP[i % len(OVERLAP)])
        await wait_quiet()
        end = await say(PROBE[i % len(PROBE)])
        reply = await voice_after(end, PROBE_LIMIT)
        r = {'round': i + 1, 'double_reply': started is not None,
             'probe_reply': None if reply is None else round(reply - end, 2),
             'thinking_after_probe': any(t > end - 0.5 for t in thinking), 'summary_updates': len(summaries)}
        results.append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)
        await wait_quiet()
    stalled = [r['round'] for r in results if r['probe_reply'] is None]
    print(f"SUMMARY 止まった回：{stalled or 'なし'}（{len(results)} 回中） 部屋：{room_name}", flush=True)
    pump_task.cancel()
    await room.disconnect()
    await lk.room.delete_room(api.DeleteRoomRequest(room=room_name))
    await lk.aclose()


if __name__ == '__main__':
    asyncio.run(main())
