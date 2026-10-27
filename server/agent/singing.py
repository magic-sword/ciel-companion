# -*- coding: utf-8 -*-
"""シエルに歌を聴いてもらう（docs/singing-evaluation-research-ja.md）。

頼まれたら（声の道具 tools/singing.py、アプリの ciel.song）、シエルが「どうぞ」と言い、そのあいだから会話モデルへの声を止めて、
マイクの声を会話サーバーの中だけでためる。歌声は OpenAI へ送らない（session.input の音声を外す）。
歌い終わり（アプリの札のタップ、SILENCE_END 秒の静けさ、MAX_SECONDS）で、歌を聴くサービス（server/singing、
同じマシンの HTTP）に渡し、返ってきた手がかりを文字にして、シエルに感想を言わせる（config/prompts/singing_feedback.md）。
会話モデルへ渡すのは手がかりの文字だけ。歌声は感想を頼んだら捨てる（ファイル・ログ・DB に残さない）。

歌っているあいだも LIVE_EVERY 秒ごとに、直近 LIVE_WINDOW 秒を歌を聴くサービスの /live に渡し、アプリへ song.live
（ときめきメーター・♡・吹き出しのひとこと）と、シエルの表情を送る（LiveCues）。歌っている人の邪魔をしないよう、声は出さない。
ひとことは決まった文から選ぶ（会話モデルを使わない。すぐ出せて、料金もかからない）。
歌い終わって分析したら、ときめき度（シエルの主観の点数）と内わけを song.result でアプリへ送り、結果のカードを出す。
"""
import asyncio
import json
import logging
import os
import time

import aiohttp
import numpy as np
from livekit import rtc

URL = os.environ.get('CIEL_SINGING_URL', 'http://127.0.0.1:8767/analyze')
LIVE_URL = os.environ.get('CIEL_SINGING_LIVE_URL', 'http://127.0.0.1:8767/live')
# 分析の前に、読み上げに作業用の GPU のメモリーを手放してもらう（同じ GPU に分析が入らないため。server/tts-irodori の /release）
TTS_RELEASE_URL = os.environ.get('CIEL_TTS_RELEASE_URL', 'http://127.0.0.1:8766/release')
TOPIC = 'ciel.song'
SR = 16000                # speakers.AudioTap と同じ
VOICE_DB = -42.0          # これより大きい 10 ms は歌声とみなす（自動で終えるため。分析の側はもっと細かく見る）
SILENCE_END = 8.0         # 歌ったあと、これだけ静かなら歌い終わり
WAIT_START = 30.0         # 「どうぞ」から、これだけ歌が始まらなければやめる
MAX_SECONDS = 600         # 長くてもここまで（分析の側も 10 分まで）
MIN_SUNG = 3.0            # 歌声がこれより短ければ、聞こえなかったことにする
ANALYZE_TIMEOUT = 120.0
LIVE_EVERY = 5.0          # 歌っているあいだ、これだけごとに直近を見る（秒）
LIVE_WINDOW = 10.0        # 見る長さ（心に響いた度は 10 秒ずつ見るモデル）
LIVE_TIMEOUT = 15.0       # 最初の 1 回はモデルを載せるので 8 秒ほどかかる
CE_LOW, CE_HIGH = 3.0, 7.0   # メーターの幅（server/singing/analysis.py の ce_level と同じ）
BUILD_DB = 3.0            # 前の 2 回より、声の芯の帯域がこれだけ強くなったら「盛り上がり」
COMMENT_GAP = 12.0        # ひとことは、これより間をあける（秒。歌の邪魔にならないように）
# 歌っている途中のひとこと（画面の吹き出し。声には出さない）。同じものは続けて出さない
COMMENTS = {
    'heart': ['ぐっときた…！', 'いまの、すごく好き！', '胸がきゅっとしたのです'],
    'build': ['盛り上がってきた！', '気持ちが乗ってきてる！'],
    'change': ['雰囲気が変わった！', 'ここから空気が変わったのです'],
    'vibrato': ['きれいなビブラート！', '伸ばす音、ゆらゆら素敵'],
    'scoop': ['しゃくり、いい感じ！', '言葉に気持ちが乗ってる'],
}
EXPRESSIONS = {'heart': 'excited', 'build': 'happy', 'change': 'surprised', 'vibrato': 'relaxed', 'scoop': 'happy'}

IDLE, LISTENING, ANALYZING = 'idle', 'listening', 'analyzing'
STARTED, ALREADY, BUSY, EMPTY, FAILED, CANCELLED = 'started', 'already', 'busy', 'empty', 'failed', 'cancelled'
LINES = {STARTED: '[歌：聴く準備ができた]', ALREADY: '[歌：もう聴いている]', BUSY: '[歌：前の歌を味わっている途中]',
         EMPTY: '[歌：歌が聞こえなかった]', FAILED: '[歌：うまく聴き取れなかった]', CANCELLED: '[歌：聴くのをやめた]'}
log = logging.getLogger('ciel-agent.singing')


def clock(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    return f'{seconds // 60}分{seconds % 60:02d}秒'


class LiveCues:
    """歌っている途中の手がかり（/live の結果）から、メーター・♡・ひとこと・表情を決める。1 曲に 1 つ"""

    def __init__(self) -> None:
        self.ces: list[float] = []
        self.bands: list[float] = []
        self.dists: list[float] = []
        self._emb: np.ndarray | None = None
        self._comment_at = -1e9
        self._last: dict[str, str] = {}

    def update(self, data: dict, at: float) -> dict | None:
        """at は歌い出しからの秒。声がほとんど無い所（息つぎ・間奏）は None"""
        ce = data.get('ce')
        if ce is None:
            return None
        reasons = []
        if len(self.ces) >= 2 and ce >= max(self.ces) and ce - float(np.median(self.ces)) >= 0.3:
            reasons.append('heart')
        band = data.get('band_db')
        if band is not None:
            if len(self.bands) >= 2 and band - float(np.mean(self.bands[-2:])) >= BUILD_DB:
                reasons.append('build')
            self.bands.append(band)
        emb = np.array(data.get('embedding') or [], np.float32)
        if len(emb):
            if self._emb is not None:
                d = 1 - float(emb @ self._emb / (np.linalg.norm(emb) * np.linalg.norm(self._emb) + 1e-9))
                if len(self.dists) >= 3 and d >= np.mean(self.dists) + np.std(self.dists) and d > 0:
                    reasons.append('change')
                self.dists.append(d)
            self._emb = emb
        if data.get('vibratos', 0) >= 1:
            reasons.append('vibrato')
        if data.get('scoops', 0) >= 2:
            reasons.append('scoop')
        self.ces.append(ce)
        event = {'v': 1, 'type': 'song.live', 'at': round(at, 1),
                 'meter': round(min(1.0, max(0.0, (ce - CE_LOW) / (CE_HIGH - CE_LOW))), 3),
                 'heart': any(r in ('heart', 'build', 'change') for r in reasons), 'comment': '', 'expression': ''}
        if reasons and at - self._comment_at >= COMMENT_GAP:
            kind = reasons[0]
            choices = [c for c in COMMENTS[kind] if c != self._last.get(kind)] or COMMENTS[kind]
            event['comment'] = choices[len(self.ces) % len(choices)]
            event['expression'] = EXPRESSIONS[kind]
            self._last[kind] = event['comment']
            self._comment_at = at
        return event


def result_card(result: dict) -> dict:
    """歌い終わったときの結果のカード（アプリの song.result）"""
    pitch = result.get('pitch') or {}
    hint = None
    if pitch.get('wobbles'):
        hint = {'kind': 'wobble', 'at': pitch['wobbles'][0]}
    elif pitch.get('off'):
        hint = {'kind': 'off', 'at': pitch['off'][0]}
    tokimeki = result.get('tokimeki') or {'score': 0, 'parts': []}
    return {'v': 1, 'type': 'song.result', 'score': tokimeki['score'], 'parts': tokimeki['parts'],
            'moments': [{'start': m['start'], 'end': m['end'], 'why': '・'.join(m['why'])} for m in result.get('moments', [])],
            'habits': '・'.join(pitch.get('habits', [])), 'duration': result.get('duration', 0),
            'hint_kind': hint['kind'] if hint else '', 'hint_at': hint['at'] if hint else -1}


def facts(result: dict) -> str:
    """歌を聴くサービスの結果を、シエルに渡す手がかりの文にする（singing_feedback.md の {facts}）"""
    lines = ['聴き取りの手がかり（数値は手がかり。読み上げない。時刻は歌い出しから）：',
             f'- 長さ：{clock(result["duration"])}（声が出ていたのは {clock(result["sung_seconds"])}）']
    if result.get('tokimeki'):
        t = result['tokimeki']
        lines.append(f'- ときめき度（シエルの主観の点数。画面にも出ている）：{t["score"]}点（'
                     + '、'.join(f'{p["name"]} {p["value"]}/{p["max"]}' for p in t['parts']) + '）')
    aes = result.get('aesthetics')
    if aes:
        windows = aes['windows']
        top = max(windows, key=lambda w: w['ce'])
        low = min(windows, key=lambda w: w['ce'])
        line = f'- 心に響いた度（この歌の中での高い・低いを見る）：平均 {aes["ce_mean"]}'
        if len(windows) > 1:
            line += (f'、いちばん高い所 {top["ce"]}（{clock(top["start"])}〜{clock(top["end"])}）'
                     f'、いちばん低い所 {low["ce"]}（{clock(low["start"])}〜{clock(low["end"])}）')
        lines.append(line)
    if result.get('moments'):
        lines.append('- ぐっときた瞬間の候補：' + '、'.join(
            f'{clock(m["start"])}〜{clock(m["end"])}（{"・".join(m["why"])}）' for m in result['moments']))
    if result.get('builds'):
        lines.append('- 盛り上がり（声の芯の響きが強くなった）：' + '、'.join(clock(t) for t in result['builds']))
    if result.get('changes'):
        lines.append('- 展開の変化（雰囲気が変わった）：' + '、'.join(clock(t) for t in result['changes']))
    if result.get('dynamics_db') is not None:
        d = result['dynamics_db']
        lines.append(f'- 強弱の幅：{"広い" if d >= 18 else "狭め" if d < 10 else "ふつう"}（{d} dB）')
    voice = result.get('voice') or {}
    if voice.get('attack'):
        lines.append('- 声の入り：' + {'soft': '柔らかい', 'medium': 'ふつう', 'hard': 'はっきりしている'}[voice['attack']])
    if voice.get('brightness_hz') is not None:
        b = voice['brightness_hz']
        lines.append(f'- 声の明るさ（目安）：{"明るめ" if b >= 1500 else "落ち着いた" if b < 700 else "ふつう"}')
    if voice.get('breath_ratio') is not None and voice['breath_ratio'] >= 0.02:
        lines.append('- 息づかい（目安）：息が多めに混ざっている')
    pitch = result.get('pitch')
    if pitch:
        habits = []
        if 'しゃくり' in pitch['habits']:
            habits.append(f'しゃくり（下から入る。音の {round(pitch["scoop_ratio"] * 100)}%）')
        if 'フォール' in pitch['habits']:
            habits.append(f'フォール（音の終わりを下げる。音の {round(pitch["fall_ratio"] * 100)}%）')
        vib = pitch['vibrato']
        if 'ビブラート' in pitch['habits'] and vib['count']:
            habits.append(f'ビブラート（{vib["count"]} 回、1 秒に {vib["rate_hz"]} 回の揺れ）')
        if habits:
            lines.append('- くせ（何度も出ている。その人の個性）：' + '、'.join(habits))
        elif vib['count']:
            lines.append(f'- ビブラート：{vib["count"]} 回')
        lines.append(f'- 音域：{pitch["range"][0]}〜{pitch["range"][1]}（伸ばす音 {pitch["long_notes"]} 個）')
        if pitch['wobbles']:
            lines.append('- 揺れた伸ばす音：' + '、'.join(clock(t) for t in pitch['wobbles']))
        if pitch['off']:
            lines.append('- 外れて聞こえたかもしれない音：' + '、'.join(clock(t) for t in pitch['off'])
                         + f'（音のうち {round(pitch["off_ratio"] * 100)}%）')
    return '\n'.join(lines)


class SongListener:
    """歌を聴いているあいだの係。1 つの会話に 1 つ（agent.py が作る）"""

    def __init__(self, session, tap, feedback: str) -> None:
        self.session = session
        self.tap = tap
        self.feedback = feedback      # config/prompts/singing_feedback.md（{facts} を手がかりで置き換える）
        self.state = IDLE
        self.publish = None           # アプリへの知らせ（agent.py がつなぐ）
        self._chunks: list[tuple[float, np.ndarray]] = []
        self._ready_at: float | None = None   # 「どうぞ」を言い終えた時刻。これより前の声は使わない（シエルの声が入る）
        self._task: asyncio.Task | None = None
        self._http: aiohttp.ClientSession | None = None
        self._live: asyncio.Task | None = None
        self._cues = LiveCues()

    @property
    def active(self) -> bool:
        return self.state != IDLE

    def start(self) -> str:
        if self.state == LISTENING:
            self._say(ALREADY)
            return ALREADY
        if self.state == ANALYZING:
            self._say(BUSY)
            return BUSY
        self.state = LISTENING
        self._chunks = []
        self._ready_at = None
        self._cues = LiveCues()
        # ここから会話モデルへ声を送らない（歌声を外へ出さない。歌っているあいだに返事もしない）
        self.session.input.set_audio_enabled(False)
        self.tap.listeners.append(self._on_chunk)
        self._notify()
        log.info('歌を聴き始める')
        self._task = asyncio.create_task(self._listen())
        return STARTED

    def finish(self) -> None:
        if self.state == LISTENING:
            self._stop()
            self.state = ANALYZING
            self._notify()
            self._task = asyncio.create_task(self._analyze())

    def cancel(self) -> None:
        if self.state == LISTENING:
            if self._task is not None:
                self._task.cancel()
            self._stop()
            self._chunks = []
            self.state = IDLE
            self._notify()
            self._say(CANCELLED)

    def on_data(self, packet: rtc.DataPacket) -> None:
        if packet.topic != TOPIC:
            return
        try:
            action = json.loads(packet.data.decode('utf-8'))['action']
        except (ValueError, KeyError, TypeError) as ex:
            log.warning('歌のメッセージを読めない: %s', ex)
            return
        if action == 'start':
            self.start()
        elif action == 'finish':
            self.finish()
        elif action == 'cancel':
            self.cancel()
        else:
            log.warning('歌の知らない操作: %s', action)

    def _on_chunk(self, t: float, pcm: np.ndarray) -> None:
        if self.state == LISTENING and self._ready_at is not None and t >= self._ready_at:
            self._chunks.append((t, pcm))

    def _stop(self) -> None:
        if self._on_chunk in self.tap.listeners:
            self.tap.listeners.remove(self._on_chunk)
        self.session.input.set_audio_enabled(True)

    async def _listen(self) -> None:
        try:
            # 「どうぞ」を言い終えてから聴く（言っているあいだの声は、シエルの声が混ざるので使わない）
            await self.session.generate_reply(instructions=LINES[STARTED], tool_choice='none')
            self._ready_at = time.time() + 0.3
            if self._http is None:
                self._http = aiohttp.ClientSession()
            await self._release_tts()   # 歌っているあいだ、分析のモデルを GPU に載せておくため
            heard_at = None
            seen = 0
            live_at = self._ready_at + LIVE_EVERY
            while self.state == LISTENING:
                await asyncio.sleep(0.25)
                now = time.time()
                for _, pcm in self._chunks[seen:]:
                    x = pcm.astype(np.float32) / 32768.0
                    if len(x) and 20 * np.log10(np.sqrt((x ** 2).mean()) + 1e-9) > VOICE_DB:
                        heard_at = now
                seen = len(self._chunks)
                if now >= live_at and (self._live is None or self._live.done()):
                    live_at = now + LIVE_EVERY
                    self._live = asyncio.create_task(self._live_step(now - self._ready_at))
                if heard_at is None and now - self._ready_at > WAIT_START:
                    log.info('歌が始まらなかった')
                    self.finish()
                elif heard_at is not None and now - heard_at > SILENCE_END:
                    log.info('静かになったので、歌い終わりとする')
                    self.finish()
                elif now - self._ready_at > MAX_SECONDS:
                    log.info('長いので、ここまでで聴き終える')
                    self.finish()
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception('歌を聴いている途中で失敗')
            if self.state == LISTENING:
                self._stop()
                self._chunks = []
                self.state = IDLE
                self._notify()
                self._say(FAILED)

    async def _live_step(self, at: float) -> None:
        """直近 LIVE_WINDOW 秒を /live に渡し、アプリへ知らせる。失敗しても歌は聴き続ける"""
        need, parts = int(LIVE_WINDOW * SR), []
        for _, pcm in reversed(self._chunks):
            parts.append(pcm)
            need -= len(pcm)
            if need <= 0:
                break
        if sum(len(p) for p in parts) < LIVE_EVERY * SR:
            return
        audio = np.concatenate(parts[::-1])
        try:
            async with self._http.post(LIVE_URL, data=audio.astype('<i2').tobytes(), headers={'X-Sample-Rate': str(SR)},
                                       timeout=aiohttp.ClientTimeout(total=LIVE_TIMEOUT)) as r:
                r.raise_for_status()
                data = await r.json()
        except Exception as e:
            log.info('歌の途中の分析ができない error=%s', type(e).__name__)
            return
        if self.state != LISTENING:
            return
        event = self._cues.update(data, at)
        if event is None or self.publish is None:
            return
        self.publish(event)
        if event['expression']:
            self.publish({'v': 1, 'type': 'character.expression', 'expression': event['expression'],
                          'intensity': 1.0, 'ttl_ms': 3000})

    async def _analyze(self) -> None:
        chunks, self._chunks = self._chunks, []
        audio = np.concatenate([c for _, c in chunks]) if chunks else np.zeros(0, np.int16)
        del chunks
        what = None
        try:
            if len(audio) < MIN_SUNG * SR:
                what = EMPTY
                return
            started = time.monotonic()
            if self._http is None:
                self._http = aiohttp.ClientSession()
            if self._live is not None:
                await asyncio.wait([self._live], timeout=LIVE_TIMEOUT)   # 歌の途中の分析と重ねない
            await self._release_tts()
            async with self._http.post(URL, data=audio.astype('<i2').tobytes(), headers={'X-Sample-Rate': str(SR)},
                                       timeout=aiohttp.ClientTimeout(total=ANALYZE_TIMEOUT)) as r:
                r.raise_for_status()
                result = await r.json()
            del audio
            log.info('歌を聴いた：%.0f 秒の歌、分析 %.1f 秒', result.get('duration', 0), time.monotonic() - started)
            if result.get('empty') or result.get('sung_seconds', 0) < MIN_SUNG:
                what = EMPTY
                return
            self.state = IDLE
            self._notify()
            if self.publish is not None:
                self.publish(result_card(result))
            self.session.generate_reply(instructions=self.feedback.replace('{facts}', facts(result)), tool_choice='none')
        except Exception as e:
            log.warning('歌を聴くサービスにつなげない error=%s', type(e).__name__)
            what = FAILED
        finally:
            if self.state != IDLE:
                self.state = IDLE
                self._notify()
            if what is not None:
                self._say(what)

    async def _release_tts(self) -> None:
        try:
            async with self._http.post(TTS_RELEASE_URL, timeout=aiohttp.ClientTimeout(total=10)) as r:
                r.raise_for_status()
                log.info('読み上げの GPU のメモリー %s', await r.json())
        except Exception as e:   # 手放せなくても分析は試す（入らなければ分析が失敗を返す）
            log.warning('読み上げの GPU のメモリーを手放せない error=%s', type(e).__name__)

    def _say(self, what: str) -> None:
        self.session.generate_reply(instructions=LINES[what], tool_choice='none')

    def _notify(self) -> None:
        if self.publish is not None:
            self.publish({'v': 1, 'type': 'song.state', 'state': self.state})

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
        if self._live is not None:
            self._live.cancel()
        if self.state == LISTENING:
            self._stop()
        self._chunks = []
        if self._http is not None:
            await self._http.close()
