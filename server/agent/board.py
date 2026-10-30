# -*- coding: utf-8 -*-
"""付箋（タスク）の一覧：頼まれたこと・シエルがしていることを、状態を持った付箋にして、みんなが同じ 1 つを見る。

それまでは、頼みは発言の文に残るだけで、それが今どうなっているかは、心が過去の発言から推し量っていた。
聞く係がもう始めた議事録の「議事録開始して」を、あとの返事で読んだ心が終了の頼みと取り違え、聞く係と心が同じ頼みを
同時に受けて「もうとっているのです」と言った（2026-10-30、bench_compare.py）。継ぎ足し（受けた頼みの一覧と文の書き換え・
「もうとっている」を言わない秒数・始めた直後の終了の確認）で合わせていたのを、ここに集める。
- 付箋は、聞く係・心の道具・アプリのボタンのどれが受けても 1 枚。同じ種類が動いていれば、新しく作らずにそれを返す。
- 状態：確認中 → 実行中 → 仕上げ中 → 完了／失敗（確認して頼みでなければ、付箋ごと外す）。
- 頼んだ発言（said）を付箋に結び付ける。心と小脳へ渡す会話では、その発言を「（→ #3 議事録をとる：実行中）」に置き換えるので、
  過去の頼みを読み直すことはない。終わった付箋は KEEP_SECONDS のあいだだけ一覧に残す（記録には発言が残る）。
- 一覧は、返事のたびに「[今のタスク]」として心と小脳へ渡し、アプリにも同じものを送る（board.state）。
今は議事録だけ（minutes.py・listener.py）。調べもの・歌・声の登録・シエルの言いたいことは、あとで同じ形で乗せる。
"""
import itertools
import logging
import time
from dataclasses import dataclass, field
from typing import Callable

import debug_log

log = logging.getLogger('ciel-agent.board')

CHECKING, RUNNING, WRAPPING, DONE, FAILED = 'checking', 'running', 'wrapping', 'done', 'failed'
ACTIVE = (CHECKING, RUNNING, WRAPPING)
LABELS = {CHECKING: '確認中', RUNNING: '実行中', WRAPPING: '仕上げ中', DONE: '完了', FAILED: '失敗'}
BY = {'listener': '話の途中の頼みを聞く係が受けた', 'ciel': 'シエルが受けた', 'app': 'アプリのボタンで'}
KEEP_SECONDS = 120.0   # 終わった付箋を一覧に残す秒数


@dataclass
class Card:
    id: int
    kind: str            # 'minutes' など
    title: str           # 「議事録をとる」
    status: str
    by: str              # BY のキー
    started: float       # time.monotonic()
    updated: float
    ref: str | None = None      # 議事録 ID など、元の係が持つ ID
    note: str = ''              # 結果のひとこと（「Discord に送った」など）
    said: list[str] = field(default_factory=list)   # この付箋を頼んだ発言の文字起こし


class Board:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.cards: list[Card] = []
        self.on_change: Callable[[dict], None] | None = None   # 変わったとき（agent.py がアプリへ送る）
        self._clock = clock
        self._ids = itertools.count(1)

    # ---- 付箋を作る・動かす ----

    def add(self, kind: str, title: str, status: str, by: str, *, said: str = '', ref: str | None = None) -> Card:
        now = self._clock()
        card = Card(next(self._ids), kind, title, status, by, now, now, ref=ref, said=[said.strip()] if said else [])
        self.cards.append(card)
        log.info('付箋：#%d %s（%s）', card.id, kind, status)
        self._changed(card)
        return card

    def move(self, card: Card, status: str, *, title: str | None = None, note: str | None = None,
             ref: str | None = None) -> None:
        card.status, card.updated = status, self._clock()
        if title is not None:
            card.title = title
        if note is not None:
            card.note = note
        if ref is not None:
            card.ref = ref
        log.info('付箋：#%d %s（%s）', card.id, card.kind, status)
        self._changed(card)

    def remove(self, card: Card) -> None:
        """確認して頼みではなかった付箋を外す"""
        if card in self.cards:
            self.cards.remove(card)
            self._changed(card, removed=True)

    def said(self, card: Card, text: str) -> None:
        """この付箋を頼んだ発言を結び付ける（送る会話で、その発言を付箋の状態に置き換える）"""
        if text.strip() and text.strip() not in card.said:
            card.said.append(text.strip())

    def find(self, kind: str, *, ref: str | None = None, statuses=ACTIVE) -> Card | None:
        """その種類の、動いている（statuses の）付箋のうち新しいもの。ref があれば、それが同じもの"""
        for card in reversed(self.cards):
            if card.kind == kind and card.status in statuses and (ref is None or card.ref == ref):
                return card
        return None

    # ---- 読む ----

    def shown(self) -> list[Card]:
        """一覧に出す付箋：動いているものと、終わってから KEEP_SECONDS のうちのもの"""
        now = self._clock()
        return [c for c in self.cards if c.status in ACTIVE or now - c.updated < KEEP_SECONDS]

    def context(self) -> str | None:
        """心と小脳へ渡す「[今のタスク]」（付箋が無ければ None）"""
        cards = self.shown()
        if not cards:
            return None
        now = self._clock()
        lines = ['[今のタスク]']
        for c in cards:
            ago = int(now - c.started)
            extra = f'。{c.note}' if c.note else ''
            lines.append(f'#{c.id} {c.title}：{LABELS[c.status]}（{BY.get(c.by, c.by)}・{ago} 秒前から{extra}）')
        return '\n'.join(lines)

    def mark(self, text: str) -> str:
        """発言のうち、付箋を頼んだ部分を「（→ #3 議事録をとる：実行中）」に置き換える（送る会話だけ。記録は変えない）"""
        for c in self.cards:
            for said in c.said:
                if said in text:
                    text = text.replace(said, f'（→ #{c.id} {c.title}：{LABELS[c.status]}）')
        return text

    def strip(self, text: str) -> str:
        """発言から、付箋を頼んだ部分を除く（頼みごととして数え直さない）"""
        for c in self.cards:
            for said in c.said:
                text = text.replace(said, '')
        return text

    def state(self) -> dict:
        """アプリへ送る一覧"""
        return {'v': 1, 'type': 'board.state',
                'cards': [{'id': c.id, 'kind': c.kind, 'title': c.title, 'status': c.status, 'by': c.by,
                           'ref': c.ref, 'note': c.note} for c in self.shown()]}

    def _changed(self, card: Card, removed: bool = False) -> None:
        debug_log.record('board', id=card.id, task=card.kind, status='removed' if removed else card.status,
                         by=card.by, title=card.title)
        if self.on_change is not None:
            try:
                self.on_change(self.state())
            except Exception:
                log.exception('付箋の一覧をアプリへ送れない')
