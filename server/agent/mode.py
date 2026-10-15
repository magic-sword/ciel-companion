# -*- coding: utf-8 -*-
"""会話のモード：2 人（solo）と多人数（group）。Unity が LiveKit のデータのメッセージ（topic ciel.mode）で知らせる。

- solo：今までどおり、話しかけられるたびに答える。
- group：会議などで何人かと話す。config/prompts/group.md の決まりを指示に足し、シエルに向けた言葉にだけ答える。
  答えないときは、会話モデルが [silent] とだけ出す。drop_silent がそれを読み上げ・文字起こしから捨てる。
  [silent] の返事は会話の履歴には残るので、黙っていたあいだの話の流れもシエルは覚えている。
- Unity は、つないだとき・会話サーバーが部屋に入ったとき・モードが変わったときに送る。同じモードが何度届いてもよい。
- 黙る仕組みは文字から声を作る方式（CIEL_VOICE=irodori）でだけ働く。ほかの方式では group を受け付けない。
"""
import asyncio
import json
import logging
import re
from collections.abc import AsyncIterable, Callable

from livekit import rtc
from livekit.agents import Agent

log = logging.getLogger('ciel-agent.mode')

TOPIC = 'ciel.mode'
MODES = {'solo', 'group'}
SILENT = '[silent]'
LEADING_TAGS = re.compile(r'(?:\s*\[[a-z]+\])*\s*')
PARTIAL_TAG = re.compile(r'\[[a-z]*')


def _decide(buf: str) -> str | None:
    """返事の頭から、黙る返事か（'silent'）、話す返事か（'speak'）を決める。まだ決められなければ None。"""
    lead = LEADING_TAGS.match(buf)
    if SILENT in lead.group():
        return 'silent'
    rest = buf[lead.end():]
    if not rest or PARTIAL_TAG.fullmatch(rest):   # 頭の印がまだ届ききっていない
        return None
    return 'speak'


async def drop_silent(text: AsyncIterable[str]) -> AsyncIterable[str]:
    """頭の印に [silent] がある返事は、まるごと捨てる。それ以外はそのまま流す。"""
    buf = ''
    decision = None
    async for chunk in text:
        if decision == 'speak':
            yield chunk
            continue
        if decision == 'silent':
            continue
        buf += str(chunk)
        decision = _decide(buf)
        if decision == 'speak':
            yield buf
        elif decision == 'silent':
            log.info('多人数の会話：シエルは黙った')
    if decision is None and buf.strip():
        yield buf


class ModeSwitch:
    def __init__(self, agent: Agent, instructions: Callable[[str], str], can_group: bool) -> None:
        self.agent = agent
        self.instructions = instructions
        self.can_group = can_group
        self.mode = 'solo'
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None   # 走っている切り替えへの参照（途中で片付けられないように持っておく）

    def on_data(self, packet: rtc.DataPacket) -> None:
        if packet.topic != TOPIC:
            return
        try:
            mode = json.loads(packet.data.decode('utf-8'))['mode']
        except (ValueError, KeyError, TypeError) as ex:
            log.warning('モードのメッセージを読めない: %s', ex)
            return
        if mode not in MODES:
            log.warning('知らないモード: %s', mode)
            return
        if mode == 'group' and not self.can_group:
            log.warning('多人数のモードは CIEL_VOICE=irodori のときだけ使える。2 人のまま続ける')
            return
        if mode == self.mode:
            return
        self.mode = mode
        log.info('会話のモード：%s', mode)
        self._task = asyncio.create_task(self._apply())

    async def _apply(self) -> None:
        # 続けて切り替えられても、最後のモードの指示で終わるように、1 つずつ順に送る
        try:
            async with self._lock:
                await self.agent.update_instructions(self.instructions(self.mode))
        except Exception as e:   # 指示を変えられなくても、会話は続ける
            log.warning('モード %s の指示に切り替えられない: %s', self.mode, e)
