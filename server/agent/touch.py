# -*- coding: utf-8 -*-
"""タッチ：Unity で相手がシエルに触れたこと（LiveKit のデータのメッセージ、topic ciel.touch）を受け取り、
会話モデルに「[タッチ] 頭を撫でる（2.4秒）」のような 1 行で知らせて、反応を話してもらう。

- 触れた瞬間の顔の動き・髪の揺れは Unity がその場で出す。ここでは声の反応だけを扱う。
- 知らせの受け取り方は config/prompts/touch.md でモデルに教える。

誰が触ったか（人は声でしか見分けられないので、声から推し量る）：
1. 触れたときに人が話していたなら、その発言への返事に「話しながら触れた」の 1 行を添える（turns.py が take で
   受け取る）。その発言の [発言者：…] の人が触ったと分かる。
2. 話していなければ、待たずに、RECENT_SECONDS 以内に話した人を「たぶん触った人」として添えて返事を作らせる。
   撫でている最中に反応できるように、話し始めるのを待たない（1.5 秒待つと、返事ができる前に撫で終わってしまった。
   2026-10-17）。触ってから話し始めた場合は、その発言に別に返事が出る。
   会議につないでいるときは添えない（会議の向こうの人は画面に触れられない）。
3. どちらでもなければ、名前を添えずに返事を作らせる。
- シエルが話している・考えている間は割り込まない（終わるまで待つ）。短い間に何度も返さないよう、間隔をあける。
- 撫でている途中（phase start）で知らせたら、撫で終わり（phase end）では知らせない。
"""
import asyncio
import json
import logging
import time

from livekit import rtc
from livekit.agents import AgentSession

import mouth

log = logging.getLogger('ciel-agent.touch')

TOPIC = 'ciel.touch'
# Unity（CielTouch）が送る部位・しぐさ。ほかの値は無視する
PARTS = {'head': '頭', 'ear': '耳', 'face': 'ほっぺ', 'cheek': 'ほっぺ', 'hair': '髪', 'shoulder': '肩', 'hand': '手'}
GESTURES = {'tap': 'ちょんとつつく', 'stroke': '撫でる', 'hold': 'そっと触れる', 'pull': 'つまんで引っ張る'}
# 引っ張る強さ（Unity が、引いた量と速さから決める）と、そのときアプリが出した表情
STRENGTHS = {'gentle': 'やさしく', 'hard': '強く'}
EXPRESSIONS = {'troubled': '困り顔', 'teary': '半泣きの顔', 'surprised': '驚いた顔', 'embarrassed': '照れた顔'}
PHASES = {'once', 'start', 'end'}   # once：tap・hold を離したとき。start・end：なぞりの始まりと終わり
COOLDOWN = 4.0         # 返事の最短の間隔（秒）
WAIT_SECONDS = 0.0     # 触れてから、話し始めるのを待つ時間（待たない）
RECENT_SECONDS = 60.0  # これより前に話した人は、触った人とみなさない
GIVE_UP_SECONDS = 10.0 # 話していた人の返事に添えられなかったら（文字にならなかったなど）、これで諦めて単独で返す


def describe(part: str, gesture: str, phase: str, duration_ms: int, strength: str = '', expression: str = '') -> str:
    how = STRENGTHS.get(strength, '')
    line = f'[タッチ] {PARTS[part]}を{how}{GESTURES[gesture]}'
    notes = []
    if phase == 'start':
        notes.append('引っ張り始めた' if gesture == 'pull' else '撫で始めた')
    elif duration_ms > 0:
        notes.append(f'{duration_ms / 1000:.1f}秒')
    if expression in EXPRESSIONS:
        notes.append(f'シエルは{EXPRESSIONS[expression]}になった')
    return line + (f'（{"。".join(notes)}）' if notes else '')


class TouchReactions:
    def __init__(self, session: AgentSession, book=None, style=None) -> None:
        self.session = session
        self.book = book      # speakers.SpeakerBook（最後に話した人。無ければ名前を添えない）
        self.style = style    # mode.ConversationStyle（会議につないでいるか）
        self.last_reply = 0.0
        self.stroke_answered = False
        self.pending: str | None = None   # まだ返事にしていない知らせ
        self._pending_at = 0.0
        self._user_spoke_at = -1.0        # 最後に人が話し始めた時刻
        self._timer: asyncio.TimerHandle | None = None

    # ---- 知らせを受ける ----

    def on_data(self, packet: rtc.DataPacket) -> None:
        if packet.topic != TOPIC:
            return
        try:
            e = json.loads(packet.data.decode('utf-8'))
            part, gesture, phase = e['part'], e['gesture'], e['phase']
            duration_ms = int(e.get('duration_ms', 0))
            strength, expression = str(e.get('strength', '')), str(e.get('expression', ''))
        except (ValueError, KeyError, TypeError) as ex:
            log.warning('タッチのメッセージを読めない: %s', ex)
            return
        if part not in PARTS or gesture not in GESTURES or phase not in PHASES:
            log.warning('知らないタッチ: %s %s %s', part, gesture, phase)
            return

        line = describe(part, gesture, phase, duration_ms, strength, expression)
        if phase == 'start':
            self.stroke_answered = True   # 撫で始め・引っ張り始めで知らせる（終わりでは知らせない）
            self._hold(line)
        elif phase == 'end':
            if not self.stroke_answered:
                self._hold(line)
            self.stroke_answered = False
        else:
            self._hold(line)

    def on_user_state(self, ev) -> None:
        if ev.new_state == 'speaking':
            self._user_spoke_at = time.monotonic()

    # ---- 返事にする ----

    def _hold(self, line: str) -> None:
        """知らせを持っておき、返せるときに返す。続けて触れたら、新しい知らせに置き換える"""
        if time.monotonic() - self.last_reply < COOLDOWN and self.pending is None:
            log.debug('タッチに返事をしない（前の返事から間もない）')
            return
        self.pending = line
        self._pending_at = time.monotonic()
        self._schedule(WAIT_SECONDS)

    def _schedule(self, seconds: float) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = asyncio.get_running_loop().call_later(seconds, self._fire)

    def _fire(self) -> None:
        self._timer = None
        if self.pending is None:
            return
        s = self.session
        now = time.monotonic()
        waited = now - self._pending_at
        spoke = self._user_spoke_at >= self._pending_at - 0.5 or s.user_state == 'speaking'
        if spoke and waited < GIVE_UP_SECONDS:
            # 触れた前後に人が話した。その発言への返事に添える（turns.py が take で受け取る）
            self._schedule(1.0)
            return
        if s.agent_state in ('speaking', 'thinking') and waited < GIVE_UP_SECONDS:
            self._schedule(0.5)   # シエルが話し終わるのを待つ
            return
        line = self.pending + self._who()
        self.pending = None
        self.last_reply = now
        log.info('タッチに返事をする%s', '（触った人を添えた）' if '触ったのは' in line else '')
        # 知らせを会話の履歴に残し、あとの会話でも触れられたことを覚えておけるようにする
        mouth.of(s).say('touch', user_input=line)

    def _who(self) -> str:
        """最後に話した人を「たぶん触った人」として添える 1 文（添えないときは空）"""
        book = self.book
        if book is None or book.last is None or (self.style is not None and self.style.meeting):
            return ''
        if time.monotonic() - getattr(book, 'last_at', -1e9) > RECENT_SECONDS:
            return ''
        sp = book.last
        if sp.name:
            return f'。触ったのは、たぶん{sp.name}さん（少し前に話していた人）'
        return f'。触ったのは、たぶん少し前に話していた人（{sp.label}）'

    def take(self) -> str | None:
        """話しながら触れたときに、その発言への返事に添える 1 行（turns.py が呼ぶ）。無ければ None"""
        if self.pending is None:
            return None
        line = self.pending + '（いま話した人が、話しながら触れた）'
        self.pending = None
        self.last_reply = time.monotonic()
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        log.info('タッチを、話した人の発言への返事に添えた')
        return line
