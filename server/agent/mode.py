# -*- coding: utf-8 -*-
"""会話のしかた。アプリの設定画面で選ぶ 2 つの設定と、その場の様子から、いまの答え方と覚えていることの出し方を決める。
Unity が LiveKit のデータのメッセージ（topic ciel.style）で知らせる。以前の ciel.mode（solo・group）も受け付ける。

おしゃべり度（talk）：
- quiet（ひかえめ）：呼ばれたときだけ答える。config/prompts/talk_quiet.md を指示に足し、turns.py が呼ばれていない発言には
  返事を作らせない。作らせても、答えないときは会話モデルが [silent] とだけ出す。drop_silent がそれを読み上げ・文字起こしから捨てる。
  [silent] の返事は会話の履歴には残るので、黙っていたあいだの話の流れもシエルは覚えている。
  黙る仕組みは文字から声を作る方式（CIEL_VOICE=irodori）でだけ働く。ほかの方式では normal にする。
- normal（ふつう）：話しかけられるたびに答える。指示は足さない。
- chatty（おしゃべり）：答えるうえに、しばらく静かだと自分からも話しかける（initiative.py）。talk_chatty.md を足す。

その場にいる人（presence）：覚えている人のメモ（speakers.py）の出し方。
- solo（ひとり）：本人のメモを渡し、シエルから話題にしてよい（presence_solo.md）。
- close（身近な人）：本人のメモを渡すが、心に留めておくだけ。話題にするよう求めない（presence_close.md）。
- public（人前）：メモを渡さない。本人に聞かれたら道具で読む（presence_public.md）。
- auto（自動）：会議の機器につないでいれば public、この会話で 2 人以上の声を聞いたら close、それ以外は solo。
  会議につないでいるあいだは、おしゃべり度も quiet にする（会議の邪魔をしない）。
いまの答え方と出し方は、変わるたびに Unity へ conversation.style（topic ciel.event）で知らせる（設定画面の「いまは：…」）。
Unity は、つないだとき・会話サーバーが部屋に入ったとき・設定が変わったときに送る。同じ設定が何度届いてもよい。
"""
import asyncio
import json
import logging
import re
from collections.abc import AsyncIterable, Callable

from livekit import rtc
from livekit.agents import Agent

log = logging.getLogger('ciel-agent.mode')

TOPIC = 'ciel.style'
LEGACY_TOPIC = 'ciel.mode'
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


class ConversationStyle:
    TALKS = ('quiet', 'normal', 'chatty')
    PRESENCES = ('auto', 'solo', 'close', 'public')

    def __init__(self, agent: Agent, instructions: Callable[[str, str], str], can_quiet: bool) -> None:
        self.agent = agent
        self.instructions = instructions   # (おしゃべり度, その場にいる人) → 会話の指示
        self.can_quiet = can_quiet
        self.talk_choice = 'normal'
        self.presence_choice = 'auto'
        self.meeting = False   # 会議の機器（仮想オーディオケーブル）につないでいる（Unity が知らせる）
        self.voices = 0        # この会話で聞いた、違う人の声の数（speakers.py の帳簿から）
        self.publish: Callable[[dict], None] | None = None   # Unity へ知らせる（agent.py がつなぐ）
        self._applied = ('normal', 'solo')
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None   # 走っている切り替えへの参照（途中で片付けられないように持っておく）

    @property
    def talk(self) -> str:
        t = self.talk_choice
        if self.meeting and self.presence_choice == 'auto':
            t = 'quiet'
        return 'normal' if t == 'quiet' and not self.can_quiet else t

    @property
    def presence(self) -> str:
        if self.presence_choice != 'auto':
            return self.presence_choice
        if self.meeting:
            return 'public'
        return 'close' if self.voices >= 2 else 'solo'

    @property
    def reason(self) -> str:
        """自動で決めたときの理由（Unity の表示用）"""
        if self.presence_choice != 'auto':
            return ''
        return 'meeting' if self.meeting else 'voices' if self.voices >= 2 else ''

    def on_data(self, packet: rtc.DataPacket) -> None:
        if packet.topic not in (TOPIC, LEGACY_TOPIC):
            return
        try:
            data = json.loads(packet.data.decode('utf-8'))
            if packet.topic == LEGACY_TOPIC:   # 以前のアプリ：solo・group
                group = data['mode'] == 'group'
                talk, presence, meeting = ('quiet' if group else 'normal'), ('public' if group else 'auto'), False
            else:
                talk, presence, meeting = data['talk'], data['presence'], bool(data.get('meeting', False))
        except (ValueError, KeyError, TypeError) as ex:
            log.warning('会話のしかたのメッセージを読めない: %s', ex)
            return
        if talk not in self.TALKS or presence not in self.PRESENCES:
            log.warning('知らない会話のしかた: %s・%s', talk, presence)
            return
        if talk == 'quiet' and not self.can_quiet:
            log.warning('ひかえめは CIEL_VOICE=irodori のときだけ使える。ふつうで続ける')
        self.talk_choice, self.presence_choice, self.meeting = talk, presence, meeting
        self._changed(force_publish=True)

    def on_voices(self, count: int) -> None:
        """この会話で聞いた声の数が変わった（turns.py が、話者を判定するたびに呼ぶ）"""
        if count != self.voices:
            self.voices = count
            self._changed()

    def _changed(self, force_publish: bool = False) -> None:
        now = (self.talk, self.presence)
        if now != self._applied:
            self._applied = now
            log.info('会話のしかた：%s・%s（選んだのは %s・%s%s）', *now, self.talk_choice, self.presence_choice,
                     f'、{self.reason}' if self.reason else '')
            self._task = asyncio.create_task(self._apply())
        elif not force_publish:
            return
        if self.publish is not None:
            self.publish({'v': 1, 'type': 'conversation.style', 'talk': self.talk, 'presence': self.presence,
                          'reason': self.reason})

    async def _apply(self) -> None:
        # 続けて切り替えられても、最後の設定の指示で終わるように、1 つずつ順に送る
        try:
            async with self._lock:
                await self.agent.update_instructions(self.instructions(*self._applied))
        except Exception as e:   # 指示を変えられなくても、会話は続ける
            log.warning('会話のしかた %s の指示に切り替えられない: %s', self._applied, e)
