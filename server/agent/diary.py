# -*- coding: utf-8 -*-
"""シエル自身に本当にあった出来事（日記）。内なる考え（initiative.py）に渡し、シエルが自分から話したいことの材料にする。

好み（config/prompts/ciel_self.md）だけでは「好き」としか話せず、思い出を作り話にすると相手の知っている事実とぶつかる
（シエルは相手のパソコンの中にいる）。そこで、シエルに本当にあったことだけを短い文で残す：
- research：気になって自分で調べて分かったこと（curiosity.py）
- song：歌を最後まで聴かせてもらったこと（singing.py）
- touch：なでてもらった・つつかれたこと（touch.py。1 回の会話で、同じ部位・しぐさは 1 度だけ）
- ゲームの名前（minecraft など）：ゲームで倒した・倒れたこと（game_env.py。ゲームの出来事の memorable。1 回の会話で、同じことは 1 度だけ）
だれと話していても同じ記録を使うので、相手の名前や事情は書かない。DB（speaker_store.Store の ciel_events）があれば
会話をまたいで残し（KEEP 個まで）、無ければその会話の間だけ覚える。
"""
import asyncio
import logging
from datetime import datetime

import debug_log
from jst import JST

log = logging.getLogger('ciel-agent.diary')

KEEP = 200        # DB に残す数（古いものから消す）
SHOW = 6          # 考える係に渡す、最近の出来事の数
TEXT_CHARS = 120


def ago(at: datetime, now: datetime) -> str:
    """「さっき」「今日」「きのう」「3 日前」のような、だいたいの時期"""
    seconds = (now - at).total_seconds()
    if seconds < 3600:
        return 'さっき'
    days = (now.astimezone(JST).date() - at.astimezone(JST).date()).days
    if days <= 0:
        return '今日'
    if days == 1:
        return 'きのう'
    return f'{days} 日前' if days < 30 else 'ずっと前'


class Diary:
    def __init__(self, store=None) -> None:
        self.store = store   # speaker_store.Store。無ければ、この会話の間だけ覚える
        self.events: list[tuple[datetime, str, str]] = []   # 新しい順に（日時、種類、文）
        self._tasks: set[asyncio.Task] = set()
        self.added = 0       # この会話で残した数（growth.py が、新しい出来事があった会話だけ好みを見直す）

    async def load(self) -> None:
        """前の会話までの出来事を読む（読めなくても会話は続ける）"""
        if self.store is None:
            return
        try:
            self.events = [(at, kind, text) for _, at, kind, text in await self.store.ciel_events(SHOW)]
        except Exception as e:
            log.warning('シエルの出来事を読めない: %s', type(e).__name__)

    def add(self, kind: str, text: str, at: datetime | None = None) -> None:
        text = ' '.join(text.split())[:TEXT_CHARS] if isinstance(text, str) else ''
        if not text:
            return
        self.events = ([(at or datetime.now(JST), kind, text)] + self.events)[:SHOW]
        self.added += 1
        log.info('シエルの出来事を残した（%s）', kind)
        debug_log.record('ciel_event', event_kind=kind, text=text)
        if self.store is not None:
            task = asyncio.create_task(self._save(kind, text))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def drain(self) -> None:
        """書いている途中の出来事を書き終えるまで待つ（会話の終わり。growth.py が読む前に）"""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _save(self, kind: str, text: str) -> None:
        try:
            await self.store.add_ciel_event(kind, text, KEEP)
        except Exception as e:
            log.warning('シエルの出来事を残せない: %s', type(e).__name__)

    def lines(self, now: datetime | None = None) -> list[str]:
        """考える係に渡す形（「きのう：気になって調べた：…」）。古い順"""
        now = now or datetime.now(JST)
        return [f'{ago(at, now)}：{text}' for at, _, text in reversed(self.events)]
