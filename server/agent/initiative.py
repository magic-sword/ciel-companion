# -*- coding: utf-8 -*-
"""シエルの内なる考え：会話の裏で、口に出さない考えを作り、話したい気持ちが強い考えだけを、会話が途切れたときに話す。

それまでは「45 秒静かなら話しかける」だけで、シエルに話したい理由が無かった。ここでは研究「Proactive Conversational
Agents with Inner Thoughts」（Liu ほか、2025）の作りに沿って、決まった時間ではなく、話したい気持ち（内的動機）で話す。
- 考える：新しい発言が確定して THINK_SETTLE_SECONDS たったら（THINK_MIN_SECONDS に 1 回まで）、軽いモデルが
  考えを 0〜3 個作り、話したい気持ち（motivation、1〜5）を付ける（config/prompts/inner_thoughts.md）。
  静かなあいだも、IDLE_THINK_SECONDS ごとに考える（話しかけて返事が無いたびに倍、IDLE_THINK_MAX まで）。
  あわせて「話している相手について、まだ知らないこと」（unknowns）を持ち、知りたいことを考えのもとにする
  （好奇心を、でたらめな話題ではなく、はっきりした知らないことに結び付ける）。
- 考えは貯めておく（MAX_THOUGHTS 個まで）。話したら印を付け、繰り返さない。
- 話す：おしゃべりのとき、PAUSE_SECONDS 以上静かで、気持ちが THRESHOLD 以上の考えがあれば、それを話題に話しかける
  （config/prompts/talk_chatty_nudge.md）。気持ちは、静かな時間が長いほど少し上がり、考えが古くなるほど下がる。
  話しかけても返事が無ければ、話すための気持ちを上げていく（しつこくしない）。人が話したら元に戻す。
  ふつうのときは、急ぎの言い直し（correction）で気持ちが 5 のものだけ（config/prompts/talk_correction_nudge.md）。
  ひかえめのときは話さないし、考えもしない。
- 人が話している最中、シエルが考え中・話している最中は話しかけない。会話の始めのあいさつの前も話しかけない。
- ログには考えの中身を出さない（数と気持ちの強さだけ）。中身はデバッグ用の会話ログ（debug_log、thoughts）にだけ残す。
決めたことは docs/decisions/inner-thoughts-ja.md。
"""
import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime

import openai
from livekit.agents import AgentSession

import debug_log
from jst import JST

log = logging.getLogger('ciel-agent.initiative')

MODEL = os.environ.get('CIEL_THOUGHT_MODEL', 'gpt-5.4-mini')
CHECK_SECONDS = 2.0
THINK_SETTLE_SECONDS = 3.0    # 新しい発言のあと、続きを待ってから考える
THINK_MIN_SECONDS = 20.0      # 考えるのは、この秒数に 1 回まで
IDLE_THINK_SECONDS = 60.0     # 静かなあいだに考える間隔（返事が無ければ倍にしていく）
IDLE_THINK_MAX = 600.0
THINK_TIMEOUT = 20.0
PAUSE_SECONDS = 8.0           # これだけ静かなら、話しかけてよい
CORRECTION_PAUSE_SECONDS = 3.0
THRESHOLD = float(os.environ.get('CIEL_THOUGHT_THRESHOLD', '4.0'))
SILENCE_STEP = 15.0           # 静かな時間がこれだけ続くごとに、気持ちを少し上げる
SILENCE_GAIN = 0.25
SILENCE_GAIN_MAX = 1.0
STALE_SECONDS = 180.0         # これより古い考えは、気持ちを下げていく
STALE_LOSS = 0.5              # STALE_SECONDS ごとに下げる量
DROP_SECONDS = 900.0          # これより古い考えは捨てる
UNANSWERED_STEP = 0.5         # 話しかけて返事が無いたびに、話すための気持ちを上げる量
UNANSWERED_MAX = 1.5
MAX_THOUGHTS = 12
CONVERSATION_TURNS = 20
KINDS = ('comment', 'question', 'recall', 'research', 'correction')
# 話しかけるときに添える、考えの種類（シエルが考えと違う話をしないように）
KIND_LABELS = {'comment': '感想', 'question': '相手に聞きたいこと', 'recall': '前の話に戻りたい',
               'research': '調べてみたいこと', 'correction': '言い直したいこと'}


@dataclass
class Thought:
    text: str
    kind: str
    motivation: float
    created: float = field(default_factory=time.monotonic)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:6])
    expressed: bool = False


class Initiative:
    def __init__(self, session: AgentSession, style, nudge: str, *, history=None, instructions: str = '',
                 correction_nudge: str = '', client=None) -> None:
        self.session = session
        self.style = style   # mode.ConversationStyle
        self.nudge = nudge
        self.correction_nudge = correction_nudge
        self.history = history   # conversation.Conversation（最近の発言）
        self.instructions = instructions
        self._client = client
        self.thoughts: list[Thought] = []
        self.expressed: list[str] = []   # 最近話した考え（繰り返さないため）
        self.unknowns: list[str] = []
        self.unanswered = 0              # 話しかけたのに返事が無かった回数
        self._last = time.monotonic()    # 最後に誰かが話していた時刻
        self._user_busy = False
        self._agent_busy = True          # あいさつが終わるまでは話しかけない
        self._seen_id = 0                # 考えに使った最後の発言 ID
        self._new_at: float | None = None   # まだ考えに使っていない発言が確定した時刻
        self._thought_at = -1e9          # 最後に考えた時刻
        self._thinking: asyncio.Task | None = None
        self._spoke_at: float | None = None   # 自分から話しかけた時刻（そのあと人が話したかで、返事を見る）
        self._task: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    def on_user_state(self, ev) -> None:
        self._user_busy = ev.new_state == 'speaking'
        self._last = time.monotonic()
        if self._user_busy:
            self.unanswered = 0      # 人が話したら、話すための気持ちを元に戻す
            self._spoke_at = None

    def on_agent_state(self, ev) -> None:
        self._agent_busy = ev.new_state in ('thinking', 'speaking', 'initializing')
        self._last = time.monotonic()

    @property
    def client(self):
        if self._client is None:
            self._client = openai.AsyncOpenAI()
        return self._client

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(CHECK_SECONDS)
            try:
                self.step(time.monotonic())
            except Exception:
                log.exception('内なる考え：失敗')

    # ---- 1 回分の見回り（テストから時刻を渡して呼べる） ----

    def step(self, now: float) -> None:
        talk = self.style.talk
        if talk == 'quiet':
            return
        self._watch_history(now)
        if self._should_think(now):
            self._thought_at = now
            self._thinking = asyncio.create_task(self._think(now))
        if self._user_busy or self._agent_busy:
            return
        thought = self.pick(now)
        if thought is not None:
            self._express(thought, now)

    def _watch_history(self, now: float) -> None:
        if self.history is None:
            return
        through = self.history.settled_through()
        if through > self._seen_id and self._new_at is None:
            self._new_at = now

    def _should_think(self, now: float) -> bool:
        if not self.instructions or (self._thinking is not None and not self._thinking.done()):
            return False
        if now - self._thought_at < THINK_MIN_SECONDS:
            return False
        if self._new_at is not None and now - self._new_at >= THINK_SETTLE_SECONDS and not self._user_busy:
            return True
        # 静かなあいだにも考える（おしゃべりのときだけ。返事が無いほど間をあける）
        idle = min(IDLE_THINK_SECONDS * 2 ** self.unanswered, IDLE_THINK_MAX)
        return (self.style.talk == 'chatty' and not self._user_busy and not self._agent_busy
                and now - self._last >= idle and now - self._thought_at >= idle)

    def score(self, t: Thought, now: float) -> float:
        """話したい気持ちの今の強さ：静かなほど少し上がり、古いほど下がり、返事が無いほど話しにくくなる"""
        silence = max(0.0, now - self._last)
        gain = min(SILENCE_GAIN * int(silence // SILENCE_STEP), SILENCE_GAIN_MAX)
        loss = STALE_LOSS * max(0.0, (now - t.created) - STALE_SECONDS) / STALE_SECONDS
        return t.motivation + gain - loss - min(UNANSWERED_STEP * self.pressure, UNANSWERED_MAX)

    @property
    def pressure(self) -> int:
        """話しかけて返事が無かった回数。前に話しかけて、まだ返事を待っているあいだも 1 回と数える"""
        return self.unanswered + (1 if self._spoke_at is not None else 0)

    def pick(self, now: float) -> Thought | None:
        """今話す考え（無ければ None）"""
        self.thoughts = [t for t in self.thoughts if now - t.created < DROP_SECONDS and not t.expressed]
        silence = now - self._last
        talk = self.style.talk
        if talk == 'chatty':
            if silence < PAUSE_SECONDS:
                return None
            best = max(self.thoughts, key=lambda t: self.score(t, now), default=None)
            return best if best is not None and self.score(best, now) >= THRESHOLD else None
        if talk == 'normal' and silence >= CORRECTION_PAUSE_SECONDS:
            return next((t for t in self.thoughts if t.kind == 'correction' and t.motivation >= 5), None)
        return None

    def _express(self, t: Thought, now: float) -> None:
        t.expressed = True
        self.expressed = (self.expressed + [t.text])[-8:]
        if self._spoke_at is not None:
            self.unanswered += 1   # 前に話しかけたあと、誰も話さなかった
        self._spoke_at = now
        self._last = now
        nudge = self.correction_nudge if t.kind == 'correction' and self.style.talk != 'chatty' else self.nudge
        log.info('内なる考え：話しかける（%s、気持ち %.1f、返事なし %d 回）', t.kind, t.motivation, self.unanswered)
        debug_log.record('thought_expressed', thought_kind=t.kind, text=t.text, motivation=t.motivation)
        note = f'[話したいこと（{KIND_LABELS[t.kind]}）] {t.text}'
        if getattr(self.session, 'current_agent', None) is None:
            self._reply(nudge, note, placed=False)
            return
        task = asyncio.create_task(self._say(nudge, note))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _say(self, nudge: str, note: str) -> None:
        """話したいことを会話の後ろに system の項目として置いてから、話しかけさせる。返事ごとの指示に足すだけだと、
        会話モデルは直前の相手の発言の続きを話してしまい、話したいことと違う話をした（2026-10-24、bench_thoughts.py）"""
        agent = self.session.current_agent
        placed = False
        try:
            ctx = agent.chat_ctx.copy()
            ctx.add_message(role='system', content=note)
            # 会話モデルの側にだけある項目（まだ手元に届いていない発言）があれば、置かない（turns.py の _add_context と同じ）
            remote = getattr(agent, 'realtime_llm_session', None)
            local_ids = {item.id for item in ctx.items}
            if remote is None or all(item.id in local_ids for item in remote.chat_ctx.items):
                await agent.update_chat_ctx(ctx)
                placed = True
        except Exception as e:
            log.warning('話したいことを会話に置けない（返事ごとの指示に足す）: %s', type(e).__name__)
        self._reply(nudge, note, placed)

    def _reply(self, nudge: str, note: str, placed: bool) -> None:
        try:
            self.session.generate_reply(instructions=nudge if placed else f'{nudge}\n\n{note}')
        except Exception as e:   # 話しかけられなくても、会話は続ける
            log.warning('話しかけられない: %s', e)

    # ---- 考える ----

    def _conversation(self) -> list[dict]:
        if self.history is None:
            return []
        rows = [t for t in self.history.between(through=self.history.settled_through()) if t.text][-CONVERSATION_TURNS:]
        return [{'speaker': t.name, 'text': t.text[:400]} for t in rows]

    async def _think(self, now: float) -> None:
        if self.history is not None:
            self._seen_id = self.history.settled_through()
        self._new_at = None
        wall = datetime.now(JST)
        request = {
            'now': f'{wall:%Y-%m-%d %H:%M}（{"月火水木金土日"[wall.weekday()]}）',
            'talk': self.style.talk,
            'silence_seconds': round(max(0.0, now - self._last)),
            'conversation': self._conversation(),
            'thoughts': [{'id': t.id, 'text': t.text, 'kind': t.kind, 'motivation': t.motivation}
                         for t in self.thoughts if not t.expressed],
            'expressed': self.expressed,
            'unknowns': self.unknowns,
        }
        try:
            r = await self.client.chat.completions.create(
                model=MODEL, reasoning_effort='low', response_format={'type': 'json_object'}, timeout=THINK_TIMEOUT,
                messages=[{'role': 'system', 'content': self.instructions},
                          {'role': 'user', 'content': json.dumps(request, ensure_ascii=False)}])
            result = json.loads(r.choices[0].message.content or '{}')
        except Exception as e:   # 考えられなくても、会話は続ける
            log.warning('内なる考え：考えられない：%s', type(e).__name__)
            return
        self.apply(result, time.monotonic())

    def apply(self, result, now: float) -> None:
        """モデルの答え（config/prompts/inner_thoughts.md の形）を、貯めている考えに当てる"""
        if not isinstance(result, dict):
            return
        by_id = {t.id: t for t in self.thoughts}
        for d in result.get('drop') or []:
            if d in by_id:
                self.thoughts.remove(by_id.pop(d))
        for r in result.get('rescore') or []:
            if isinstance(r, dict) and r.get('id') in by_id:
                by_id[r['id']].motivation = _motivation(r.get('motivation'), by_id[r['id']].motivation)
        added = 0
        for raw in result.get('thoughts') or []:
            if added >= 3:
                break
            if not isinstance(raw, dict) or not isinstance(raw.get('text'), str) or not raw['text'].strip():
                continue
            text = raw['text'].strip()[:80]
            if any(t.text == text for t in self.thoughts) or text in self.expressed:
                continue
            kind = raw.get('kind') if raw.get('kind') in KINDS else 'comment'
            self.thoughts.append(Thought(text, kind, _motivation(raw.get('motivation'), 1.0), created=now))
            added += 1
        self.thoughts = sorted(self.thoughts, key=lambda t: -t.motivation)[:MAX_THOUGHTS]
        unknowns = result.get('unknowns')
        if isinstance(unknowns, list):
            self.unknowns = [u.strip()[:60] for u in unknowns if isinstance(u, str) and u.strip()][:8]
        top = max((t.motivation for t in self.thoughts), default=0)
        log.info('内なる考え：%d 個足した（貯めている %d 個、いちばん強い気持ち %.0f、知りたいこと %d 個）',
                 added, len(self.thoughts), top, len(self.unknowns))
        debug_log.record('thoughts', thoughts=[{'text': t.text, 'kind': t.kind, 'motivation': t.motivation}
                                                for t in self.thoughts], unknowns=self.unknowns)


def _motivation(value, default: float) -> float:
    try:
        return max(1.0, min(5.0, float(value)))
    except (TypeError, ValueError):
        return default
