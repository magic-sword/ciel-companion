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
import json
import logging
import math
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
# 日記（diary.py）に残すときの言い方
DIARY_GESTURES = {'tap': 'ちょんとつつかれた', 'stroke': 'なでてもらった', 'hold': 'そっと触れてもらった', 'pull': 'つまんで引っ張られた'}
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
        self._source_epoch = None
        self._source_seq = -1
        self.last_reply = 0.0
        self.stroke_answered = False
        self.pending: str | None = None   # まだ返事にしていない知らせ
        self._pending_at = 0.0
        self.diary = None                 # diary.Diary（なでてもらったことを残す。agent.py がつなぐ）
        self._noted: set[tuple[str, str]] = set()   # この会話で日記に残した（部位、しぐさ）

    # ---- 知らせを受ける ----

    def on_data(self, packet: rtc.DataPacket) -> None:
        if packet.topic != TOPIC:
            return
        try:
            e = json.loads(packet.data.decode('utf-8'))
            if type(e.get('v')) is not int or e.get('v') != 2 or e.get('type') != 'user.touch':
                mouth.of(self.session).reactions.reject('touch', 'unsupported_touch_contract')
                return
            if not isinstance(e.get('event_id'), str) or not isinstance(e.get('source_epoch'), str) or type(e.get('seq')) is not int:
                return
            if not 1 <= len(e['event_id']) <= 160 or not 1 <= len(e['source_epoch']) <= 160:
                return
            if type(e.get('occurred_at')) not in (int, float) or not math.isfinite(e['occurred_at']):
                return
            now = mouth.of(self.session).reactions.wall()
            if now - e['occurred_at'] > 5 or e['occurred_at'] > now + 1:
                return
            if self._source_epoch is not None and self._source_epoch != e['source_epoch']:
                return
            if e['seq'] <= self._source_seq:
                return
            part, gesture, phase = e['part'], e['gesture'], e['phase']
            if not all(isinstance(value, str) for value in (part, gesture, phase)):
                return
            duration_ms = int(e.get('duration_ms', 0))
            strength, expression = str(e.get('strength', '')), str(e.get('expression', ''))
        except (ValueError, KeyError, TypeError) as ex:
            log.warning('タッチのメッセージを読めない: %s', ex)
            return
        if part not in PARTS or gesture not in GESTURES or phase not in PHASES:
            log.warning('知らないタッチ: %s %s %s', part, gesture, phase)
            return

        self._source_epoch, self._source_seq = e['source_epoch'], e['seq']
        self._incoming = e
        line = describe(part, gesture, phase, duration_ms, strength, expression)
        if self.diary is not None and phase != 'end' and (part, gesture) not in self._noted:
            self._noted.add((part, gesture))   # だれが触ったかは書かない（diary.py）
            self.diary.add('touch', f'{PARTS[part]}を{DIARY_GESTURES[gesture]}')
        if phase == 'start':
            self.stroke_answered = True   # 撫で始め・引っ張り始めで知らせる（終わりでは知らせない）
            self._hold(line)
        elif phase == 'end':
            if not self.stroke_answered:
                self._hold(line)
            self.stroke_answered = False
        else:
            self._hold(line)

    def _hold(self, line: str) -> None:
        if time.monotonic() - self.last_reply < COOLDOWN and self.pending is None:
            return
        self.pending = line
        self._pending_at = time.monotonic()
        hub = mouth.of(self.session).reactions
        kind = 'touch.pull' if self._incoming.get('gesture') == 'pull' and self._incoming.get('strength') == 'hard' else 'touch.contact'
        envelope = hub.envelope('touch', kind, {'fact': line}, event_id=self._incoming['event_id'])
        envelope['occurred_at'] = self._incoming['occurred_at']
        self._reaction = hub.receive('touch', envelope, why='touch',
            kwargs={'user_input': line + self._who()}, settle=WAIT_SECONDS,
            expression=self._incoming.get('expression') if self._incoming.get('expression') in EXPRESSIONS else None,
            local_expression=True)

    def reset(self):
        self._source_epoch, self._source_seq = None, -1
        self.pending = None
        mouth.of(self.session).reactions.reset('touch')


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
        event = mouth.of(self.session).reactions.take('touch')
        if self.pending is None or event is None:
            self.pending = None
            return None
        line = self.pending + '（いま話した人が、話しながら触れた）'
        self.pending = None
        self.last_reply = time.monotonic()
        log.info('タッチを、話した人の発言への返事に添えた')
        return line
