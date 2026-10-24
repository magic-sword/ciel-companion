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
- 話す頃合い：沈黙を待たない（人の会話では、話し手が替わる間はほぼ 0.2 秒以内。何秒も黙っていれば人のほうが話す。
  Inner Thoughts の論文も、沈黙は頃合いの手がかりとして当てにならないと書いている）。シエルに話す番が来た瞬間に話す：
  1. 返事に添える：シエルが相手に返事をするとき、気持ちが THRESHOLD 以上の考えを「言えたら添えたいこと」として渡し、
     流れに合えば返事の最後に一言添えさせる（offer。turns.py が返事を頼むときに呼ぶ。
     config/prompts/talk_offer.md）。
  2. 話し終えた直後に続ける：シエルが相手への返事を話し終えて、CONTINUE_AFTER〜CONTINUE_WINDOW 秒のあいだ相手が
     話し始めなければ、気持ちが CONTINUE_THRESHOLD（5）以上の考えを続けて話す（話し手交替の規則の「誰も話し始めなければ、
     今の話し手が続けてよい」。Sacks ほか 1974）。シエルが自分から話しかけたあとには続けない（ひとりで話し続けない）。
  回数の上限は持たず、話したい欲の満腹度で決める（SATIETY_HALF_LIFE の説明）。自分から話すたびに満腹度が上がり、
  時間とともに下がる。返事に添えた考えは、次に考えるときに会話から「実際に話したか」を確かめ（spoken）、話していれば
  満腹度を上げ、話していなければ気持ちを下げて残す（毎回の返事に足すと多すぎた。2026-10-24、bench_thoughts.py）。
  3. 長い沈黙：FALLBACK_SECONDS 誰も話さなければ、話しかける（最後の手段）。
  気持ちは、静かな時間が長いほど少し上がり、考えが古くなるほど下がる（config/prompts/talk_chatty_nudge.md）。
  話しかけても返事が無ければ、話すための気持ちを上げていく（しつこくしない）。人が話したら元に戻す。
  ふつうのときは、急ぎの言い直し（correction）で気持ちが 5 のものだけ（config/prompts/talk_correction_nudge.md）。
  ひかえめのときは話さないし、考えもしない。
- 人が話している最中、シエルが考え中・話している最中は話しかけない。会話の始めのあいさつの前も話しかけない。
- ログには考えの中身を出さない（数と気持ちの強さだけ）。中身はデバッグ用の会話ログ（debug_log、thoughts）にだけ残す。
決めたことは docs/decisions/inner-thoughts-ja.md、参考にした研究と設計の原点は docs/inner-thoughts-research-ja.md。
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
CHECK_SECONDS = 0.5
THINK_SETTLE_SECONDS = 3.0    # 新しい発言のあと、続きを待ってから考える
THINK_MIN_SECONDS = 20.0      # 考えるのは、この秒数に 1 回まで
IDLE_THINK_SECONDS = 60.0     # 静かなあいだに考える間隔（返事が無ければ倍にしていく）
IDLE_THINK_MAX = 600.0
THINK_TIMEOUT = 20.0
CONTINUE_AFTER = 1.5          # シエルが話し終えて、相手がこれだけ話し始めなければ、続けて話してよい
CONTINUE_WINDOW = 4.0         # 続けて話すのは、話し終えてからこの秒数まで（過ぎたら、長い沈黙を待つ）
FALLBACK_SECONDS = 30.0       # 誰もこれだけ話さなければ、話しかける（最後の手段）
CONTINUE_THRESHOLD = float(os.environ.get('CIEL_THOUGHT_CONTINUE_THRESHOLD', '5.0'))   # 続けて話す気持ちの強さ
CORRECTION_PAUSE_SECONDS = 3.0
THRESHOLD = float(os.environ.get('CIEL_THOUGHT_THRESHOLD', '4.0'))
SILENCE_STEP = 15.0           # 静かな時間がこれだけ続くごとに、気持ちを少し上げる
SILENCE_GAIN = 0.25
SILENCE_GAIN_MAX = 1.0
STALE_SECONDS = 180.0         # これより古い考えは、気持ちを下げていく
STALE_LOSS = 0.5              # STALE_SECONDS ごとに下げる量
DROP_SECONDS = 900.0          # これより古い考えは捨てる
# 話したい欲の満腹度（欲求と恒常性。社会的ロボット Kismet（Breazeal 2003）などの作り）。シエルが自分から話す
# （話しかける・続ける・返事に添えた考えを実際に話す）たびに上がり、時間とともに半分ずつ下がる。話す条件は
# 「気持ち − 満腹度 ≥ 基準」なので、話した直後は話しにくく、時間がたてばまた話せる。回数の上限は持たない
SATIETY_HALF_LIFE = float(os.environ.get('CIEL_THOUGHT_SATIETY_HALF_LIFE', '90'))
SATE_SPEAK = 1.0              # 自分から 1 回話したときに上がる量
SATE_UNANSWERED = 0.5         # 前に話しかけて返事が無いまま、また話したときに足す量（気まずさ）
UNUSED_OFFER_LOSS = 1.0       # 返事に添えるよう渡したのに使われなかった考えの気持ちを下げる量
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
    offered: bool = False   # 返事に添えるよう渡して、実際に話したかをまだ確かめていない


class Initiative:
    def __init__(self, session: AgentSession, style, nudge: str, *, history=None, instructions: str = '',
                 correction_nudge: str = '', offer_note: str = '', client=None) -> None:
        self.session = session
        self.style = style   # mode.ConversationStyle
        self.nudge = nudge
        self.correction_nudge = correction_nudge
        self.offer_note = offer_note   # 返事に添えるときの指示（config/prompts/talk_offer.md）
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
        self._agent_done_at: float | None = None   # シエルが相手への返事を話し終えた時刻（続けて話してよいかを見る）
        self.satiety = 0.0                 # 話したい欲の満腹度（_satiated_at の時点の値。satiety_at で今の値）
        self._satiated_at = time.monotonic()

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
        if getattr(ev, 'old_state', None) == 'speaking' and ev.new_state != 'speaking':
            # 相手への返事を話し終えた（自分から話しかけたあとは、続けない）
            self._agent_done_at = self._last if self._spoke_at is None else None
        elif ev.new_state == 'speaking':
            self._agent_done_at = None

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
        """話したい気持ちの今の強さ：静かなほど少し上がり、古いほど下がり、話したばかりなら下がる（満腹度）"""
        silence = max(0.0, now - self._last)
        gain = min(SILENCE_GAIN * int(silence // SILENCE_STEP), SILENCE_GAIN_MAX)
        loss = STALE_LOSS * max(0.0, (now - t.created) - STALE_SECONDS) / STALE_SECONDS
        return t.motivation + gain - loss - self.satiety_at(now)

    def satiety_at(self, now: float) -> float:
        return self.satiety * 0.5 ** (max(0.0, now - self._satiated_at) / SATIETY_HALF_LIFE)

    def _sate(self, now: float, amount: float) -> None:
        self.satiety = self.satiety_at(now) + amount
        self._satiated_at = now

    def continuing(self, now: float) -> bool:
        """シエルが相手への返事を話し終えて、相手がまだ話し始めていない（続けて話してよい）"""
        done = self._agent_done_at
        return (done is not None and self._last <= done and not self._user_busy
                and CONTINUE_AFTER <= now - done <= CONTINUE_WINDOW)

    def pick(self, now: float) -> Thought | None:
        """今話す考え（無ければ None）"""
        self.thoughts = [t for t in self.thoughts if now - t.created < DROP_SECONDS and not t.expressed]
        candidates = [t for t in self.thoughts if not t.offered]   # 返事に添えたばかりの考えは、話したか分かるまで待つ
        silence = now - self._last
        talk = self.style.talk
        if talk == 'chatty':
            if silence >= FALLBACK_SECONDS:
                threshold = THRESHOLD
            elif self.continuing(now):
                # 続けて話すのは、とても話したいことだけ（気持ち 4 の考えは、次の返事に添える）
                threshold = CONTINUE_THRESHOLD
            else:
                return None
            best = max(candidates, key=lambda t: self.score(t, now), default=None)
            return best if best is not None and self.score(best, now) >= threshold else None
        if talk == 'normal' and silence >= CORRECTION_PAUSE_SECONDS:
            return next((t for t in candidates if t.kind == 'correction' and t.motivation >= 5), None)
        return None

    def offer(self) -> str | None:
        """相手への返事に添える考え（turns.py が返事を頼むときに呼ぶ）。添えるなら、返事ごとの指示に足す 1 段落"""
        if self.style.talk != 'chatty' or not self.offer_note:
            return None
        now = time.monotonic()
        if any(t.offered for t in self.thoughts):
            return None   # 前に渡した考えを話したか、まだ確かめていない
        fresh = [t for t in self.thoughts if not t.expressed and t.kind != 'correction' and now - t.created < DROP_SECONDS]
        best = max(fresh, key=lambda t: t.motivation, default=None)
        if best is None or best.motivation - self.satiety_at(now) < THRESHOLD:
            return None
        # 実際に話したかは、次に考えるときに会話から確かめる（apply の spoken）。話していれば満腹度を上げる
        best.offered = True
        log.info('内なる考え：返事に添える（%s、気持ち %.1f、満腹度 %.1f）', best.kind, best.motivation, self.satiety_at(now))
        debug_log.record('thought_offered', thought_kind=best.kind, text=best.text, motivation=best.motivation)
        return f'{self.offer_note}\n[言えたら添えたいこと（{KIND_LABELS[best.kind]}）] {best.text}'

    def snapshot(self) -> dict:
        """道具 read_inner_thoughts の答え：話したい気持ちの強い考え・知りたいこと・満たされ具合（数字は出さない）"""
        now = time.monotonic()
        top = sorted((t for t in self.thoughts if not t.expressed), key=lambda t: -self.score(t, now))[:5]
        satiety = self.satiety_at(now)
        return {'thoughts': [{'text': t.text, 'kind': KIND_LABELS[t.kind],
                              'want': 'とても話したい' if t.motivation >= 5 else '話したい' if t.motivation >= 4 else 'すこし'}
                             for t in top],
                'unknowns': self.unknowns,
                'talk_drive': '話したばかりで満たされている' if satiety >= 1.5 else 'すこし満たされている' if satiety >= 0.5 else 'ふつう'}

    def keep(self, text, kind: str = 'question') -> str:
        """道具 keep_thought：会話モデルが、あとで話したいことを考えとして預ける"""
        text = text.strip()[:80] if isinstance(text, str) else ''
        if not text:
            return 'invalid'
        if any(t.text == text for t in self.thoughts):
            return 'already_kept'
        self.thoughts.append(Thought(text, kind if kind in KINDS and kind != 'correction' else 'question', 4.0))
        self.thoughts = sorted(self.thoughts, key=lambda t: -t.motivation)[:MAX_THOUGHTS]
        log.info('内なる考え：会話モデルが考えを預けた（%s）', kind)
        debug_log.record('thought_kept', thought_kind=kind, text=text)
        return 'kept'

    def _express(self, t: Thought, now: float) -> None:
        self._agent_done_at = None   # 続けて話すのは 1 回だけ
        t.expressed = True
        self.expressed = (self.expressed + [t.text])[-8:]
        if self._spoke_at is not None:
            self.unanswered += 1   # 前に話しかけたあと、誰も話さなかった
        self._sate(now, SATE_SPEAK + (SATE_UNANSWERED if self._spoke_at is not None else 0.0))
        self._spoke_at = now
        self._last = now
        nudge = self.correction_nudge if t.kind == 'correction' and self.style.talk != 'chatty' else self.nudge
        log.info('内なる考え：話しかける（%s、気持ち %.1f、返事なし %d 回、満腹度 %.1f）',
                 t.kind, t.motivation, self.unanswered, self.satiety_at(now))
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
            'thoughts': [{'id': t.id, 'text': t.text, 'kind': t.kind, 'motivation': t.motivation,
                          **({'offered': True} if t.offered else {})} for t in self.thoughts if not t.expressed],
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
        # 返事に添えるよう渡した考えを、シエルが実際に話したか（話していれば満腹度を上げる。話していなければ気持ちを下げる）
        spoken = {i for i in result.get('spoken') or [] if isinstance(i, str)}
        for t in list(self.thoughts):
            if t.id in spoken:
                t.expressed = True
                self.expressed = (self.expressed + [t.text])[-8:]
                if t.offered:
                    self._sate(now, SATE_SPEAK)
                    log.info('内なる考え：返事に添えた考えを話した（%s）', t.kind)
                    debug_log.record('thought_spoken', thought_kind=t.kind, text=t.text)
                self.thoughts.remove(t)
                by_id.pop(t.id, None)
            elif t.offered:
                t.offered = False
                t.motivation = max(1.0, t.motivation - UNUSED_OFFER_LOSS)
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
