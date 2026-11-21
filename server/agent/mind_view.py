# -*- coding: utf-8 -*-
"""心の考え（システム2）：シエルが今何を考え、何を話し出そうとしているかをアプリへ送る（mind.ideas、topic ciel.event）。

なぜ：心が考えた話したいことと、その点・理由・話したか落としたかが、外から見えなかった（2026-11-21）。会話ログ
（debug_log の mind_ideas・speak_up）は本番ではふだん残らない。アプリの会話グラフの窓（CielProcessWindow.cs）が読む。

- 相手の発言ごとに 1 枚。新しい順に KEEP 枚まで送る。
- 段：返事を待つ（心はシエルの返事を読んでから考える）→ 考え中 → 考えた → 話す予定・話した・落とした・止めた。
- 中身は会話ログと同じ（ログと画面が食い違わない）。記憶の候補・選んだ記憶は送らない。
- presence を一緒に送る。ひとり（solo）以外では、アプリが考えの文を隠して種類と点だけを見せる。
"""
from __future__ import annotations

import itertools
import time
import uuid
from collections import deque
from typing import Callable

VERSION = 1
KEEP = 3
HEARD_CHARS = 40


def _join(items) -> str:
    return '／'.join(str(x) for x in items or [] if str(x).strip())


class MindView:
    def __init__(self, notify: Callable[[dict], None] | None, *, presence: Callable[[], str] = lambda: '',
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.notify, self.presence, self.clock = notify, presence, clock
        self.stream_id, self.revision = uuid.uuid4().hex, 0
        self.threshold: float | None = None   # 自分から話す基準（speak_up.SpeakUp.threshold）
        self.speak = False                    # 段階3（自分から話す）が動いているか
        self._cards: deque[dict] = deque(maxlen=KEEP)
        self._ids = itertools.count(1)

    def _card(self, turn: int, heard: str | None = None) -> dict:
        card = next((c for c in self._cards if c['turn'] == turn), None)
        if card is None:
            card = {'id': next(self._ids), 'turn': turn, 'heard': '', 'phase': 'waiting_reply', 'reason': '',
                    'ms': 0.0, 'ideas': [], 'chosen': -1, 'at': self.clock()}
            self._cards.appendleft(card)
        if heard:
            text = ' '.join(heard.split())
            card['heard'] = text if len(text) <= HEARD_CHARS else text[:HEARD_CHARS - 1] + '…'
        return card

    # ---- 心（recall.MindRecall）から ----

    def waiting(self, turn: int, heard: str) -> None:
        """返事を読んでから考えるので、シエルの返事ができるのを待っている"""
        if any(c['turn'] == turn for c in self._cards):
            return   # 待つ間、心は何度も見に来る。知らせるのは最初の 1 回
        self._card(turn, heard)
        self.publish()

    def thinking(self, turn: int, heard: str) -> None:
        card = self._card(turn, heard)
        card['phase'], card['reason'] = 'thinking', ''
        self.publish()

    def thought(self, turn: int, ideas, ms: float) -> None:
        card = self._card(turn)
        card['ideas'] = [{'kind': i.kind, 'text': i.text, 'pro': _join(i.pro), 'con': _join(i.con),
                          'score': i.score, 'weighted': round(i.weighted, 2) if i.weighted is not None else -1.0,
                          'level': round(i.level, 2)} for i in ideas]
        card['phase'] = 'thought' if ideas else 'none'
        card['ms'] = round(ms, 1)
        if ideas:
            card['chosen'] = max(range(len(ideas)), key=lambda k: ideas[k].level)
        self.publish()

    # ---- 自分から話す（speak_up.SpeakUp）から ----

    def outcome(self, turn: int, status: str, reason: str = '', threshold: float | None = None) -> None:
        """status：scheduled（話す言葉を頼んだ）・spoken・dropped・aborted"""
        card = next((c for c in self._cards if c['turn'] == turn), None)
        if threshold is not None:
            self.threshold = threshold
        if card is None:
            return
        card['phase'], card['reason'] = status, reason or ''
        self.publish()

    # ---- 送る ----

    def state(self) -> dict:
        now = self.clock()
        return {'v': VERSION, 'type': 'mind.ideas', 'stream_id': self.stream_id, 'revision': self.revision,
                'presence': self.presence() or '', 'speak': self.speak,
                'threshold': round(self.threshold, 2) if self.threshold is not None else -1.0,
                'cards': [{k: v for k, v in c.items() if k != 'at'} | {'ago': round(now - c['at'], 1)}
                          for c in self._cards]}

    def publish(self) -> None:
        if self.notify is None:
            return
        self.revision += 1
        self.notify(self.state())
