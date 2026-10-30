# -*- coding: utf-8 -*-
"""シエルの小脳と心（CIEL_MODEL=pipeline のとき）。返事を作るたびに、会話の記録（conversation.Conversation）から文脈を組み立てる。

Realtime の組み立てでは、会話モデルが自分の会話をもう 1 つ持ち、そこへ話者の行・時刻・議事録の状態・心の状態を
system の項目として差し込んで合わせていた（記録が 2 つ。docs/attention-and-thinking-design-ja.md の 2 章）。
ここでは、LiveKit が持つ会話からは今回の分（今回の発言・今回だけの指示・道具の呼び出し）だけを使い、ほかは記録から作る。

返事は 2 つの係で作る（研究 Talker-Reasoner の形。速く話す係と、裏で考える係を分ける）。
- 小脳（すぐの返事）：ふつうの発言に返す。短い指示（人物像・話し方・config/prompts/talker.md）と、心が書いた「今のまとめ」と、
  最近の発言だけを読み、道具は持たない。黙るときは [silent]。
- 心（考える番）：全部の指示と道具で返す。どちらで返すかはコードが決める（route）：頼みごとの言葉がある・長く話した・何人も話した・
  ひかえめで名前を呼ばれた・議事録や歌の知らせ・道具の結果を受けた続き。小脳に「考えるべきか」を [think] で言わせる作りは、
  2 回の試験で一度も [think] を出さず、議事録を頼まれて道具なしで「準備しますね」と答えたのでやめた（2026-10-30）。
- 今のまとめ：心が、発言が増えたら（summaries/live.py と同じ決め方）会話を読み直して書く（config/prompts/mind_brief.md）。
  小脳は最近の発言しか読まないので、会話全体の流れはここで伝える。
"""
import re
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
DEEP_WHY = ('minutes', 'song', 'enrolled')   # 心が返事を作る、口（mouth.py）の why
LONG_SECONDS = 10.0        # これだけ長く話したら、心が考えて返す
LONG_CHARS = 80
# 「シエル」。文字起こしの聞き間違いも含める（gpt-realtime-whisper は名前のヒントを渡せず「シェル」「シェアル」になった。2026-10-30）
NAME = re.compile(r'シエル|しえる|シェル|シェアル|チエル|ciel|\bCL\b', re.IGNORECASE)
# 道具が要る頼みごとの言葉（議事録・調べもの・時刻・名前・覚えていること・歌）。あれば心が返す
REQUEST = re.compile(r'録|まとめ|調べ|検索|何時|時間を|名前|覚えて|忘れて|歌')
BRIEF_LABELS = (('topic', '話題'), ('flow', '流れ'), ('decided', '決まったこと'), ('open', 'まだ決まっていないこと'),
                ('people', '人'), ('say', 'シエルが言いたいこと'))


class Mind:
    def __init__(self, history, *, style=None, minutes=None, initiative=None, quiet_turn: str = '',
                 brief_instructions: str = '', client=None) -> None:
        self.history = history        # conversation.Conversation（唯一の記録）
        self.style = style            # mode.ConversationStyle
        self.minutes = minutes        # minutes.Minutes
        self.initiative = initiative  # initiative.Initiative（心の状態。段階 3 で記録に移す）
        self.quiet_turn = quiet_turn  # ひかえめのときの念押し（config/prompts/talk_quiet_turn.md）
        self.brief_instructions = brief_instructions   # config/prompts/mind_brief.md
        self._client = client
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
        """口が返事を頼む直前（mouth.Mouth.before_say）。議事録・歌の知らせ・声の登録の一言は、心が作る"""
        if why in DEEP_WHY:
            self._deep = True

    def route(self, chat_ctx: llm.ChatContext, turn: dict | None = None) -> str:
        """この返事を心（'mind'）と小脳（'talker'）のどちらが作るか（コードで決める）。turn は turns.py の pipeline_turn"""
        tail = _tail(list(chat_ctx.items))
        if any(getattr(i, 'type', None) == 'function_call_output' for i in tail):
            return 'mind'   # 道具の結果を受けた続き
        if self._deep:
            self._deep = False
            return 'mind'
        text = ''.join(_text(i) for i in tail if getattr(i, 'role', None) == 'user')
        if not text:
            return 'talker'   # 自分から話しかける・タッチなど、相手の発言の無い返事
        # ひかえめ（会議）では、何人も話したことは心に回す理由にしない（人どうしの話に心が意見を言った。2026-10-30）
        quiet = self.style is not None and self.style.talk == 'quiet'
        why = ('request' if REQUEST.search(text)
               else 'long' if (turn or {}).get('seconds', 0.0) >= LONG_SECONDS or len(text) >= LONG_CHARS
               else 'people' if not quiet and self._speakers_since_ciel() >= 2
               else 'named' if quiet and NAME.search(text)
               else None)
        if why is None:
            return 'talker'
        log.info('心：考えて返す（%s）', why)
        debug_log.record('mind_route', why=why)
        return 'mind'

    def _speakers_since_ciel(self) -> int:
        """シエルが最後に話してから話した人の数（話者が分からない発言は数えない）"""
        names = set()
        for t in reversed(self.history.turns if self.history is not None else []):
            if t.role == 'assistant' and t.text:
                break
            if t.role == 'user' and t.text and t.speaker is not None:
                names.add(id(t.speaker))
        return len(names)

    # ---- 文脈 ----

    def build(self, chat_ctx: llm.ChatContext, *, talker_instructions: str | None = None,
              turn: dict | None = None) -> llm.ChatContext:
        """LiveKit が渡した会話（会話の指示＋LiveKit が持つ発言＋今回の分）から、送る会話を作る。
        talker_instructions があれば小脳（会話の指示をこれに替え、最近の発言を少なく）、無ければ心（全部の指示）。
        turn（turns.py の pipeline_turn）の話者の 1 行・タッチは、今回の発言の前に置く（LiveKit の会話は書き換えない）"""
        items = list(chat_ctx.items)
        instructions = next((i for i in items if getattr(i, 'role', None) == 'system'), None)
        tail = [i for i in _tail(items) if i is not instructions]
        tail_users = {_text(i) for i in tail if getattr(i, 'role', None) == 'user'}
        turn = turn or {}
        self.memory = turn.get('memory')
        out = llm.ChatContext()
        if talker_instructions is not None:
            out.add_message(role='system', content=talker_instructions)
        elif instructions is not None:
            out.items.append(instructions)
        for t in self._recent(TALKER_TURNS if talker_instructions is not None else DEEP_TURNS):
            text = t.text[:TURN_CHARS]
            if t.role == 'user':
                if any(text in u for u in tail_users):
                    continue   # 今回の発言（の切れ端）は、LiveKit の側の分を使う
                out.add_message(role='user', content=f'{t.name}：{text}')
            else:
                out.add_message(role='assistant', content=text)
        notes = self._notes(deep=talker_instructions is None)
        if notes:
            out.add_message(role='system', content=notes)
        speaker = '\n'.join(x for x in (turn.get('tag'), turn.get('touch')) if x)
        if speaker and tail_users:
            out.add_message(role='system', content=speaker)   # 今回の発言の話者（とタッチ）
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

