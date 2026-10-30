# -*- coding: utf-8 -*-
"""シエルの小脳と心（CIEL_MODEL=pipeline のとき）。返事を作るたびに、会話の記録（conversation.Conversation）から文脈を組み立てる。

Realtime の組み立てでは、会話モデルが自分の会話をもう 1 つ持ち、そこへ話者の行・時刻・議事録の状態・心の状態を
system の項目として差し込んで合わせていた（記録が 2 つ。docs/attention-and-thinking-design-ja.md の 2 章）。
ここでは、LiveKit が持つ会話からは今回の分（今回の発言・今回だけの指示・道具の呼び出し）だけを使い、ほかは記録から作る。

返事は 2 つの係で作る（研究 Talker-Reasoner の形。速く話す係と、裏で考える係を分ける）。
- 小脳（すぐの返事）：発言のたびに呼ぶ。短い指示（人物像・話し方・config/prompts/talker.md）と、心が書いた「今のまとめ」と、
  最近の発言だけを読み、道具は持たない。全部の指示（約 1 万 3 千トークン）と道具 26 個を毎回読ませると、返事が
  約 1〜2 秒遅れた（2026-10-30、bench_compare.py）。黙るときは [silent]、考える・道具が要るときは [think] とだけ返す。
- 心（考える番）：小脳が [think] と言ったとき（考える相づちを流してから）・議事録や歌の知らせのとき・道具の結果を受けたときに、
  全部の指示と道具で返事を作る（config/prompts/mind_turn.md）。
- 今のまとめ：心が、発言が増えたら（summaries/live.py と同じ決め方）会話を読み直して書く（config/prompts/mind_brief.md）。
  小脳は最近の発言しか読まないので、会話全体の流れはここで伝える。
"""
import asyncio
import json
import logging
import time
from datetime import datetime

import openai
from livekit.agents import llm

import clock
import debug_log
import models
from jst import JST
from summaries import live

log = logging.getLogger('ciel-agent.mind')

TALKER_TURNS = 16          # 小脳に渡す最近の発言の数
DEEP_TURNS = 40            # 心に渡す最近の発言の数
TURN_CHARS = 1200          # 1 つの発言から渡す文字数
BRIEF_TURNS = 60           # 今のまとめを書くときに渡す発言の数（前に書いてからの分）
BRIEF_TIMEOUT = 20.0
THINK = '[think]'
DEEP_WHY = ('mind', 'minutes', 'song', 'enrolled')   # 心が返事を作る、口（mouth.py）の why
BRIEF_LABELS = (('topic', '話題'), ('flow', '流れ'), ('decided', '決まったこと'), ('open', 'まだ決まっていないこと'),
                ('people', '人'), ('say', 'シエルが言いたいこと'))


class Mind:
    def __init__(self, history, *, style=None, minutes=None, initiative=None, quiet_turn: str = '',
                 brief_instructions: str = '', turn_instructions: str = '', say=None, think=None, client=None) -> None:
        self.history = history        # conversation.Conversation（唯一の記録）
        self.style = style            # mode.ConversationStyle
        self.minutes = minutes        # minutes.Minutes
        self.initiative = initiative  # initiative.Initiative（心の状態。段階 3 で記録に移す）
        self.quiet_turn = quiet_turn  # ひかえめのときの念押し（config/prompts/talk_quiet_turn.md）
        self.brief_instructions = brief_instructions   # config/prompts/mind_brief.md
        self.turn_instructions = turn_instructions     # config/prompts/mind_turn.md
        self.say = say                # 口（mouth.Mouth.say）。考える番の返事を頼む
        self.think = think            # 考える相づちを流す（aizuchi.Backchannel.think）
        self._client = client
        self.memory: str | None = None   # 今回の話者について覚えていること（turns.py の pipeline_turn が入れる）
        self.brief: str | None = None    # 今のまとめ（心が書く）
        self._brief_raw: dict = {}
        self._brief_through = 0          # 今のまとめに使った最後の発言 ID
        self._brief_at = time.monotonic()
        self._briefing: asyncio.Task | None = None
        self._deep = False               # 次の返事は心が作る
        self._state: str | None = None   # 最後に受け取った心の状態（initiative）
        self._task: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()

    @property
    def client(self):
        if self._client is None:
            self._client = openai.AsyncOpenAI()
        return self._client

    # ---- 小脳と心の振り分け ----

    def on_say(self, why: str) -> None:
        """口が返事を頼む直前（mouth.Mouth.before_say）。議事録・歌の知らせ・考える番は、心が作る"""
        if why in DEEP_WHY:
            self._deep = True

    def deep_turn(self, chat_ctx: llm.ChatContext) -> bool:
        """この返事を心が作るか。道具の結果を受けた続きの返事も、心が作る"""
        if any(getattr(i, 'type', None) == 'function_call_output' for i in _tail(list(chat_ctx.items))):
            return True
        deep, self._deep = self._deep, False
        return deep

    async def talk(self, stream):
        """小脳の返事を流す。頭が [think] なら流さず、考える相づちを流して、心に考える番の返事を頼む"""
        held, text = [], ''
        async for chunk in stream:
            if held is None:
                yield chunk
                continue
            held.append(chunk)
            text += _chunk_text(chunk)
            lead = text.lstrip()
            if not lead or THINK.startswith(lead):
                continue   # まだ決められない（[think] の書きかけかもしれない）
            if lead.startswith(THINK):
                self._handoff()
                return
            for c in held:
                yield c
            held = None
        if held:
            for c in held:
                yield c

    def _handoff(self) -> None:
        log.info('心：小脳が考える番にした')
        debug_log.record('mind_handoff')
        if self.think is not None:
            self.think()
        if self.say is not None:
            self.say('mind', instructions=self.turn_instructions, tool_choice='auto')

    # ---- 文脈 ----

    def build(self, chat_ctx: llm.ChatContext, *, talker_instructions: str | None = None) -> llm.ChatContext:
        """LiveKit が渡した会話（会話の指示＋LiveKit が持つ発言＋今回の分）から、送る会話を作る。
        talker_instructions があれば小脳（会話の指示をこれに替え、最近の発言を少なく）、無ければ心（全部の指示）"""
        items = list(chat_ctx.items)
        instructions = next((i for i in items if getattr(i, 'role', None) == 'system'), None)
        tail = [i for i in _tail(items) if i is not instructions]
        tail_users = {_text(i) for i in tail if getattr(i, 'role', None) == 'user'}
        out = llm.ChatContext()
        if talker_instructions is not None:
            out.add_message(role='system', content=talker_instructions)
        elif instructions is not None:
            out.items.append(instructions)
        for t in self._recent(TALKER_TURNS if talker_instructions is not None else DEEP_TURNS):
            text = t.text[:TURN_CHARS]
            if t.role == 'user':
                if any(u.endswith(text) for u in tail_users):
                    continue   # 今回の発言は、LiveKit の側の分（話者を添えたもの）を使う
                out.add_message(role='user', content=f'{t.name}：{text}')
            else:
                out.add_message(role='assistant', content=text)
        notes = self._notes(deep=talker_instructions is None)
        if notes:
            out.add_message(role='system', content=notes)
        out.items.extend(tail)
        return out

    def _recent(self, n: int):
        if self.history is None:
            return []
        rows = [t for t in self.history.turns if t.ready.is_set() and t.text and t.role in ('user', 'assistant')]
        return rows[-n:]

    def _notes(self, deep: bool) -> str:
        """今回の返事のための補足（会話の後ろ、今回の発言の前に置く）"""
        lines = [clock.now_line()]
        if self.brief:
            lines.append(self.brief)
        if self.initiative is not None:
            note = self.initiative.state_note()
            if note is not None:
                self._state = note
            if self._state and self.style is not None and self.style.talk == 'chatty':
                lines.append(self._state)
        if deep and self.minutes is not None:
            lines.append(self.minutes.context())
            note = self.minutes.take_note()
            if note:
                lines.append(note)
        if self.memory:
            lines.append(self.memory)
        if self.style is not None and self.style.talk == 'quiet' and self.quiet_turn:
            lines.append(self.quiet_turn)
        return '\n\n'.join(line for line in lines if line)

    # ---- 今のまとめ ----

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(live.LIVE_POLL_SECONDS)
            try:
                self.step(time.monotonic())
            except Exception:
                log.exception('心：今のまとめの見回りに失敗')

    def step(self, now: float) -> None:
        if self.history is None or not self.brief_instructions:
            return
        if self._briefing is not None and not self._briefing.done():
            return
        through = self.history.settled_through()
        new = sum(1 for t in self.history.between(self._brief_through, through) if t.role == 'user' and t.text)
        if not live.due(new, now - self._brief_at):
            return
        self._brief_at = now
        self._briefing = asyncio.create_task(self._write_brief(through))

    async def _write_brief(self, through: int) -> None:
        rows = [t for t in self.history.between(self._brief_through, through) if t.text][-BRIEF_TURNS:]
        wall = datetime.now(JST)
        request = {
            'now': f'{wall:%Y-%m-%d %H:%M}',
            'talk': self.style.talk if self.style is not None else 'normal',
            **({'previous': self._brief_raw} if self._brief_raw else {}),
            'conversation': [{'speaker': t.name, 'text': t.text[:TURN_CHARS]} for t in rows],
            **({'thoughts': self._state} if self._state else {}),
        }
        model = models.model('brief')
        try:
            r = await self.client.chat.completions.create(
                model=model, reasoning_effort='low', response_format={'type': 'json_object'}, timeout=BRIEF_TIMEOUT,
                messages=[{'role': 'system', 'content': self.brief_instructions},
                          {'role': 'user', 'content': json.dumps(request, ensure_ascii=False)}])
            models.record('brief', model, getattr(r, 'usage', None))
            result = json.loads(r.choices[0].message.content or '{}')
        except Exception as e:   # 書けなくても、会話は続ける（次の機会に回す）
            log.warning('心：今のまとめを書けない：%s', type(e).__name__)
            return
        self.apply_brief(result, through)

    def apply_brief(self, result, through: int) -> None:
        if not isinstance(result, dict):
            return
        raw = {k: result[k].strip()[:300] for k, _ in BRIEF_LABELS if isinstance(result.get(k), str) and result[k].strip()}
        self._brief_raw, self._brief_through = raw, through
        lines = [f'{label}：{raw[k]}' for k, label in BRIEF_LABELS if k in raw]
        self.brief = '\n'.join(['[今のまとめ]', *lines]) if lines else None
        log.info('心：今のまとめを書いた（%d 項目）', len(lines))
        debug_log.record('mind_brief', brief=self.brief)


def _tail(items: list) -> list:
    """今回の分：最後のシエルの返事より後ろ（今回の発言・今回だけの指示・道具の呼び出しと結果）"""
    last = max((n for n, i in enumerate(items) if getattr(i, 'role', None) == 'assistant'), default=-1)
    return items[last + 1:]


def _text(item) -> str:
    return (getattr(item, 'text_content', None) or '').strip()


def _chunk_text(chunk) -> str:
    if isinstance(chunk, str):
        return chunk
    delta = getattr(chunk, 'delta', None)
    return (getattr(delta, 'content', None) or '') if delta is not None else ''
