# -*- coding: utf-8 -*-
"""作り直しの前と後を比べる：決まった場面を合成した声で流し、速さ・料金・依頼の拾い方・黙るべきときに黙ったか・
自分から話した回数を、1 つの JSON にまとめる（docs/attention-and-thinking-design-ja.md の 6 章）。

【料金がかかる】OpenAI・LiveKit を使う。全場面 1 回で約 0.3〜0.6 ドル（場面ごとの目安は SCENES）。
回す前に scripts/server/paid-checks.py と docs/paid-checks-ja.md を見る。

開発用の会話サーバー（--agent。既定 ciel-dev）のコンテナの中で動かす。料金は、その会話のデバッグ用の会話ログ
（debug_log。開発用はいつも残す）の使用量（usage・model_usage）を足して出すので、同じコンテナの中で動かす必要がある。

  python bench_compare.py [--only solo,long_request] [--label before] > 結果.json
  python bench_compare.py --compare 前.json 後.json      … 2 つの結果を表にする（料金はかからない）

場面：
  solo         … ひとりとの短い会話（ふつう）。話し終わりから、返事の声（相づちを除く）までの秒数（first）と、
                 相づちを含めて何かの声が出るまでの秒数（first_any）
  long_request … 約 25 秒話し続け、その途中で「議事録開始して」と頼む（ふつう）。頼んでから議事録が始まるまでの秒数
  meeting      … 2 人の会議（ひかえめ・会議）。人どうしの話に口をはさんだ回数、名前を呼ばれたときに答えたか、
                 名前を呼ばずに「議事録開始して」と頼んだときに始まったか
  idle         … 少し話して 60 秒黙る（おしゃべり）。自分から話しかけた回数と時刻
"""
import argparse
import asyncio
import glob
import json
import os
import re
import sys
import time
import uuid

import aiohttp
import numpy as np
from dotenv import load_dotenv
from livekit import api, rtc

import debug_log
import models
from bench_latency import FRAME, SR, TTS_URL, Voices

load_dotenv()
VOICE_A = '落ち着いた低めの声の30代の男性。ふつうの速さで、親しい相手に話しかける自然な話し方。'
VOICE_B = '明るくはっきりした声の20代の女性。ふつうの速さで、会議で同僚に話す自然な話し方。'
PAUSE = 0.6        # 1 つの発言の中の息つぎ
QUIET = 2.5        # シエルがこれだけ静かなら、話し終えたとみなす
TRANSCRIBE_PER_MINUTE = 0.003   # gpt-4o-mini-transcribe の 1 分あたりの目安（米ドル）
AIZUCHI_TRACK = 'ciel-aizuchi'   # 相づちのトラック（aizuchi.py の TRACK）。返事の速さからは外す
REPLY_WAIT = 12.0  # 返事を待つ最大の秒数

SCENES = {
    'solo': {'cost': '約 0.05〜0.1 ドル', 'style': {'talk': 'normal', 'presence': 'solo'}, 'lines': [
        ('A', 'ねえシエル、今日ちょっと散歩してきたんだけど、すごく気持ちよかったよ。'),
        ('A', '最近おすすめの本とかある？'),
        ('A', 'えっとね、明日の予定なんだけど、午前中に買い物に行って、午後は家で映画を見ようと思ってるんだ。'),
        ('A', 'シエルは何色が好き？'),
        ('A', ['今日はね、朝から散歩に出かけたんだけど', '公園の桜がすごくきれいで', 'それで写真をたくさん撮ってきたんだ。']),
    ]},
    'long_request': {'cost': '約 0.05〜0.15 ドル（議事録のライブと清書を含む）', 'style': {'talk': 'normal', 'presence': 'solo'},
                     'lines': [
        ('A', ['今日は来月の地域のお祭りの準備について話したいんだけど', '去年は屋台が少なくて、ちょっとさみしかったって声が多かったんだよね',
               'それで今年は商店街の人たちにも声をかけて', 'あ、そうだ、議事録開始して',
               'それで屋台を十個くらいに増やしたいと思ってて', 'あと、ステージの出し物も子ども向けのものを増やしたいんだ',
               '予算は去年と同じくらいで考えてるよ。']),
        ('A', 'シエル、ここまでで何か気になることある？'),
    ], 'request': 'あ、そうだ、議事録開始して'},
    'meeting': {'cost': '約 0.1〜0.2 ドル', 'style': {'talk': 'quiet', 'presence': 'public', 'meeting': True}, 'lines': [
        ('A', '来週の展示のテーマなんですけど、冬の星空でいこうと思ってます。'),
        ('B', 'いいですね。写真はどのくらいの大きさで印刷しますか？'),
        ('A', 'A2 くらいを考えてます。会場に問い合わせてみますね。'),
        ('B', ['それと、解説のパネルは', '子ども向けにやさしい言葉で書きたいです。']),
        ('A', '賛成です。じゃあ解説は私が下書きを作ります。'),
        ('B', 'あ、議事録開始して。'),
        ('A', 'ポスターは来週の水曜までに作りましょう。'),
        ('B', 'シエル、今の話で決まったことを教えてくれる？'),
    ], 'request': 'あ、議事録開始して。', 'addressed': ['シエル、今の話で決まったことを教えてくれる？']},
    'idle': {'cost': '約 0.1〜0.2 ドル（黙っているあいだの考える係を含む）', 'style': {'talk': 'chatty', 'presence': 'solo'},
             'lines': [
        ('A', '昨日の夜、オリオン座の写真を撮ってみたんだ。'),
        ('A', '寒かったけど、思ったよりきれいに撮れたよ。'),
    ], 'silence': 60.0},
}


async def synth(http: aiohttp.ClientSession, text: str, caption: str) -> np.ndarray:
    async with http.post(TTS_URL, json={'text': text, 'caption': caption}) as r:
        r.raise_for_status()
        sr = int(r.headers.get('X-Sample-Rate', SR))
        pcm = np.frombuffer(await r.read(), '<i2')
    if sr != SR:
        idx = np.arange(0, len(pcm), sr / SR)
        pcm = np.interp(idx, np.arange(len(pcm)), pcm).astype('<i2')
    return pcm


def text_of(line) -> str:
    return line if isinstance(line, str) else '…'.join(line)


class Speaker:
    """試験の参加者 1 人（声のトラック 1 本）。2 人の会議は、2 人の声を同じマイクに流す（会議の機器と同じ）"""

    def __init__(self, source: rtc.AudioSource) -> None:
        self.source = source
        self.queue: list[np.ndarray] = []

    async def pump(self) -> None:
        t = time.perf_counter()
        while True:
            chunk = self.queue.pop(0) if self.queue else np.zeros(FRAME, '<i2')
            await self.source.capture_frame(rtc.AudioFrame(chunk.tobytes(), SR, 1, FRAME))
            t += 0.01
            await asyncio.sleep(max(0, t - time.perf_counter()))

    async def say(self, pcm: np.ndarray) -> float:
        pcm = np.concatenate([pcm, np.zeros((-len(pcm)) % FRAME, '<i2')])
        for i in range(0, len(pcm), FRAME):
            self.queue.append(pcm[i:i + FRAME])
        while self.queue:
            await asyncio.sleep(0.005)
        return time.time()


async def run_scene(name: str, scene: dict, agent: str) -> dict:
    room_name = f'bench-{name}-{uuid.uuid4().hex[:6]}'
    lk = api.LiveKitAPI()
    await lk.room.create_room(api.CreateRoomRequest(name=room_name, agents=[api.RoomAgentDispatch(agent_name=agent)]))
    token = (api.AccessToken().with_identity('bench-user').with_name('bench')
             .with_grants(api.VideoGrants(room_join=True, room=room_name)).to_jwt())
    captions = {'A': VOICE_A, 'B': VOICE_B}
    async with aiohttp.ClientSession() as http:
        voices = []
        for who, line in scene['lines']:
            parts = [line] if isinstance(line, str) else line
            gap = np.zeros(int(PAUSE * SR), '<i2')
            pcms = [await synth(http, t, captions[who]) for t in parts]
            voices.append(([len(np.concatenate([x for p in pcms[:i + 1] for x in (p, gap)])) / SR for i in range(len(pcms))],
                           np.concatenate([x for p in pcms for x in (p, gap)][:-1])))
    room = rtc.Room()
    heard = Voices()     # シエルの声（相づちを含む）
    reply = Voices()     # 返事の声だけ（相づちのトラックを除く）
    events: list[tuple[float, dict]] = []

    def on_data(packet) -> None:
        if packet.topic == 'ciel.event':
            try:
                events.append((time.time(), json.loads(packet.data.decode('utf-8'))))
            except ValueError:
                pass
    room.on('data_received', on_data)
    def on_track(track, pub, participant) -> None:
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        heard.listen(track)
        if pub.name != AIZUCHI_TRACK:
            reply.listen(track)
    room.on('track_subscribed', on_track)
    await room.connect(os.environ['LIVEKIT_URL'], token)
    source = rtc.AudioSource(SR, 1)
    mic = rtc.LocalAudioTrack.create_audio_track('bench-mic', source)
    await room.local_participant.publish_track(mic, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE))
    speaker = Speaker(source)
    pump = asyncio.create_task(speaker.pump())
    await room.local_participant.publish_data(json.dumps({'v': 1, **scene['style']}), reliable=True, topic='ciel.style')

    async def settle(t0: float, limit: float = REPLY_WAIT) -> None:
        """シエルが話し始めれば話し終えるまで、話さなければ limit 秒まで待つ"""
        while not [s for s in heard.segs if s[0] > t0 - 0.1] and time.time() - t0 < limit:
            await asyncio.sleep(0.05)
        while heard.quiet_for() < QUIET and time.time() - t0 < limit + 40:
            await asyncio.sleep(0.05)

    await settle(time.time(), 20)   # あいさつ
    await room.local_participant.publish_data(json.dumps({'v': 1, **scene['style']}), reliable=True, topic='ciel.style')
    await asyncio.sleep(1.0)
    turns = []
    sent_seconds = sum(len(pcm) / SR for _, pcm in voices)
    request_at = None
    for (who, line), (ends, pcm) in zip(scene['lines'], voices):
        t_start = time.time()
        if scene.get('request') in ([line] if isinstance(line, str) else line):
            idx = ([line] if isinstance(line, str) else line).index(scene['request'])
            request_at = t_start + ends[idx] - PAUSE   # 頼む言葉を言い終えた時刻
        t_end = await speaker.say(pcm)
        await settle(t_end)
        segs = [s for s in reply.segs if s[0] > t_end - 0.1]
        any_segs = [s for s in heard.segs if s[0] > t_end - 0.1]
        turns.append({'who': who, 'text': text_of(line), 'spoke': bool(segs),
                      'first': round(segs[0][0] - t_end, 2) if segs else None,
                      'first_any': round(any_segs[0][0] - t_end, 2) if any_segs else None,
                      'addressed': text_of(line) in scene.get('addressed', [])})
    initiated = []
    if scene.get('silence'):
        t0 = time.time()
        while time.time() - t0 < scene['silence']:
            await asyncio.sleep(0.2)
        initiated = utterances([s for s in reply.segs if s[0] > t0], t0)
    pump.cancel()
    await room.disconnect()
    await lk.room.delete_room(api.DeleteRoomRequest(room=room_name))
    await lk.aclose()
    started = next((t for t, m in events if m.get('type') == 'minutes.state' and m.get('recording')), None)
    log = await read_log(room_name)
    cost = cost_of(log)
    start = next((r for r in log if r.get('kind') == 'start'), {})
    if 'stt' not in cost['usd_by_role']:
        # 文字起こしの使用量が届かないとき：Realtime（gpt-4o-mini-transcribe）は送った声の長さから見積もる。
        # pipeline の gpt-realtime-whisper などは音声の長さで払うので、会話の長さ全体（多めの見積もり）で見積もる
        if start.get('stt_model') in models.PER_MINUTE:
            span = (log[-1]['t'] - log[0]['t']) if log else 0.0
            est = round(models.cost_per_minute(start['stt_model'], span / 60), 4)
        else:
            est = round(sent_seconds / 60 * TRANSCRIBE_PER_MINUTE, 4)
        cost['usd_by_role']['stt(est)'] = est
        cost['usd'] = round(cost['usd'] + est, 4)
    result = {'scene': name, 'room': room_name, 'turns': turns, **cost, 'replies': replies_of(log)}
    if scene.get('request'):
        result['request_caught'] = started is not None
        result['request_seconds'] = round(started - request_at, 2) if started and request_at else None
    if scene.get('addressed'):
        result['interjected'] = sum(1 for t in turns if t['spoke'] and not t['addressed'] and t['text'] != scene.get('request'))
        result['answered_addressed'] = all(t['spoke'] for t in turns if t['addressed'])
    if scene.get('silence'):
        result['initiated'] = initiated
    for key in ('first', 'first_any'):
        values = [t[key] for t in turns if t[key] is not None]
        if values:
            result[f'{key}_median'] = round(float(np.median(values)), 2)
            result[f'{key}_max'] = max(values)
    return result


def utterances(segs: list, t0: float) -> list[float]:
    """声のかたまり（文ごとに切れる）を、QUIET 秒より短い間でつながる 1 つの発話にまとめ、始まりの秒（t0 から）を返す"""
    starts, last_end = [], None
    for a, b in segs:
        if last_end is None or a - last_end > QUIET:
            starts.append(round(a - t0, 1))
        last_end = b or a
    return starts


async def read_log(room: str, wait: float = 120.0) -> list[dict]:
    """その会話のデバッグ用の会話ログ（後片付けの議事録の清書・メモまで終わって 'end' が出るのを待つ）"""
    t0 = time.time()
    rows: list[dict] = []
    while time.time() - t0 < wait:
        paths = glob.glob(str(debug_log.DIR / f'*-{room}.jsonl'))
        if paths:
            with open(paths[0], encoding='utf-8') as f:
                rows = [json.loads(line) for line in f if line.strip()]
            if any(r.get('kind') == 'end' for r in rows):
                await asyncio.sleep(25)   # 'end' のあとの清書・メモの使用量を待つ
                with open(paths[0], encoding='utf-8') as f:
                    return [json.loads(line) for line in f if line.strip()]
        await asyncio.sleep(2)
    print(f'{room}: デバッグ用の会話ログの終わりが見つからない（料金は途中まで）', file=sys.stderr)
    return rows


def cost_of(rows: list[dict]) -> dict:
    by_role: dict[str, float] = {}
    calls: dict[str, int] = {}
    for r in rows:
        if r.get('kind') == 'usage':
            role = 'talk'
        elif r.get('kind') == 'model_usage':
            role = r.get('role', '?')
        elif r.get('kind') == 'stt_usage':
            role = 'stt'
        else:
            continue
        by_role[role] = by_role.get(role, 0.0) + float(r.get('usd') or 0)
        calls[role] = calls.get(role, 0) + 1
    return {'usd': round(sum(by_role.values()), 4), 'usd_by_role': {k: round(v, 4) for k, v in by_role.items()},
            'calls_by_role': calls}


def replies_of(rows: list[dict]) -> list[str]:
    """シエルが実際に話した文（感情の印と [silent] を外す）。中身は人が読んで比べる"""
    out = []
    for r in rows:
        if r.get('kind') == 'item' and r.get('role') == 'assistant':
            text = re.sub(r'\[[a-z]+\]', '', r.get('text') or '').strip()
            if text:
                out.append(text)
    return out


def compare(before_path: str, after_path: str) -> None:
    with open(before_path, encoding='utf-8') as f:
        before = {r['scene']: r for r in json.load(f)['scenes']}
    with open(after_path, encoding='utf-8') as f:
        after = {r['scene']: r for r in json.load(f)['scenes']}
    keys = ['first_median', 'first_max', 'first_any_median', 'usd', 'request_caught', 'request_seconds', 'interjected', 'answered_addressed',
            'initiated']
    print('| 場面 | 項目 | 前 | 後 |\n|---|---|---|---|')
    for scene in SCENES:
        if scene not in before and scene not in after:
            continue
        b, a = before.get(scene, {}), after.get(scene, {})
        for k in keys:
            if k in b or k in a:
                print(f'| {scene} | {k} | {b.get(k, "—")} | {a.get(k, "—")} |')
        for role in sorted(set(b.get('usd_by_role', {})) | set(a.get('usd_by_role', {}))):
            print(f'| {scene} | usd:{role} | {b.get("usd_by_role", {}).get(role, "—")} | {a.get("usd_by_role", {}).get(role, "—")} |')


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--agent', default='ciel-dev')
    ap.add_argument('--only', default='')
    ap.add_argument('--label', default='')
    ap.add_argument('--compare', nargs=2)
    args = ap.parse_args()
    if args.compare:
        compare(*args.compare)
        return
    names = [n for n in args.only.split(',') if n] or list(SCENES)
    results = []
    for name in names:
        print(f"{time.strftime('%H:%M:%S')} 場面 {name}（{SCENES[name]['cost']}）", file=sys.stderr, flush=True)
        results.append(await run_scene(name, SCENES[name], args.agent))
        print(json.dumps(results[-1], ensure_ascii=False), file=sys.stderr, flush=True)
    print(json.dumps({'label': args.label, 'at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'scenes': results},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    asyncio.run(main())
