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
  1. 返事に気持ちを混ぜる：シエルが相手に返事をするとき、今の心の状態（気になっていること・知りたいこと・話したい
     気持ちの満たされ具合）を会話の後ろに置いておき、流れに合えば自然に話題にさせる（state_note・place_state。
     turns.py が返事を頼むときに呼ぶ。config/prompts/talk_inner_state.md）。「言えたら添えて」という用事として
     渡していたときは、会話モデルがほとんど使わなかった。
  2. 話し終えた直後に続ける：シエルが相手への返事を話し終えて、CONTINUE_AFTER〜CONTINUE_WINDOW 秒のあいだ相手が
     話し始めなければ、気持ちが CONTINUE_THRESHOLD（5）以上の考えを続けて話す（話し手交替の規則の「誰も話し始めなければ、
     今の話し手が続けてよい」。Sacks ほか 1974）。シエルが自分から話しかけたあとには続けない（ひとりで話し続けない）。
  回数の上限は持たず、話したい欲の満腹度で決める（SATIETY_HALF_LIFE の説明）。自分から話すたびに満腹度が上がり、
  時間とともに下がる。心の状態に載せた考えは、次に考えるときに会話から「実際に話したか」を確かめ（spoken）、話していれば
  満腹度を上げ、話していなければ気持ちを下げて残す（毎回の返事に足すと多すぎた。2026-10-24、bench_thoughts.py）。
  3. 長い沈黙：FALLBACK_SECONDS 誰も話さなければ、話しかける（最後の手段）。
  気持ちは、静かな時間が長いほど少し上がり、考えが古くなるほど下がる（config/prompts/talk_chatty_nudge.md）。
  話しかけても返事が無ければ、話すための気持ちを上げていく（しつこくしない）。人が話したら元に戻す。
  ふつうのときは、急ぎの言い直し（correction）で気持ちが 5 のものだけ（config/prompts/talk_correction_nudge.md）。
  ひかえめのときは話さないし、考えもしない。
- 人が話している最中、シエルが考え中・話している最中は話しかけない。会話の始めのあいさつの前も話しかけない。
- ログには考えの中身を出さない（数と気持ちの強さだけ）。中身はデバッグ用の会話ログ（debug_log、thoughts）にだけ残す。
付箋の形（CIEL_MODEL=pipeline。board をつなぐと、こちらになる）：沈黙の秒数で話さず、満腹度も使わない。
- 気になっていること（上の state_note と同じ選び方）を「気になっている」の付箋にする（board.py）。小脳も心も、ふつう・
  おしゃべりのどちらでも、相手への返事で流れに合えば話題にする（今までの心の状態は、おしゃべりのときだけだった）。
- 話す番（返事を話し終えて相手が話し始めない間）が来て、気になっている付箋があれば、心に話すかを決めさせる
  （config/prompts/initiative_open.md。話す価値が無ければ [silent]）。気持ちが 5 かどうかの決まりで止めない。
- おしゃべりのときは、静かなあいだに強い考え（気持ち 5）が新しく浮かんだことも、話す番にする（時間ではなく出来事）。
  話しかけて返事が無ければ、相手が話すまで待つ。長い沈黙の最後の手段（FALLBACK_SECONDS）は使わない。
- 話したかは、今までどおり次に考えるときに確かめる（spoken）。話していれば付箋ごと外す。
- 調べてみたいこと（research）で調べる質問があれば、まず自分で調べる（curiosity.py）。調べているあいだは付箋にしない。
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

import board
import debug_log
import models
import mouth
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
# （話しかける・続ける・心の状態に載せた考えを実際に話す）たびに上がり、時間とともに半分ずつ下がる。話す条件は
# 「気持ち − 満腹度 ≥ 基準」なので、話した直後は話しにくく、時間がたてばまた話せる。回数の上限は持たない
SATIETY_HALF_LIFE = float(os.environ.get('CIEL_THOUGHT_SATIETY_HALF_LIFE', '90'))
SATE_SPEAK = 1.0              # 自分から 1 回話したときに上がる量
SATE_UNANSWERED = 0.5         # 前に話しかけて返事が無いまま、また話したときに足す量（気まずさ）
UNUSED_OFFER_LOSS = 0.5       # 心の状態に載せたのに話されなかった考えの気持ちを下げる量（何度か載るので小さめ）
# 用済みの考えを残さない（2026-10-24、会話の始めの「呼ばれたのです、何か用かな？」が後まで残り、返事に添えられた）。
# 古さは時間だけでなく、会話の進み方で決める：考えには、きっかけの発言（anchor。考えたときに確定していた最後の発言 ID）を持たせる
REACTIVE_KINDS = ('comment', 'correction')   # その発言への反応。相手がそのあと REACTIVE_TURNS 回話したら用済み
REACTIVE_TURNS = 2
UNREVIEWED_LOSS = 1.0         # 考える係が、前の考えを付け直しも捨てもしなかったら、気持ちをこれだけ下げる
TOPIC_SHIFT_LOSS = 1.0        # 話題が移ったとき、前の話題の聞きたいこと・戻りたいことの気持ちを下げる量
MAX_THOUGHTS = 12
BOARD_THOUGHTS = 2            # 付箋にする、気になっていることの数
PER_TOPIC_KIND = 2             # 同じ話題・同じ種類の考えを持つ数
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
    offered: bool = False   # 心の状態に載せて、実際に話したかをまだ確かめていない
    anchor: int = 0         # きっかけの発言 ID（考えた・付け直したときに確定していた最後の発言）
    shown_id: int = 0       # 心の状態に載せたときの最後の発言 ID（話したかは、これより後のシエルの発言だけで判定する）
    topic: str = ''         # 考えたときの話題（話題が移ったら、その話題への反応は用済み）
    stimulus: str = ''      # 何をきっかけにした考えか（相手の発言の中身・覚えていること・知りたいこと）
    query: str = ''         # 調べてみたいこと（research）の、Web で調べる質問（curiosity.py が自分で調べる）
    researching: bool = False   # 今、自分で調べている


class Initiative:
    def __init__(self, session: AgentSession, style, nudge: str, *, history=None, instructions: str = '',
                 correction_nudge: str = '', state_header: str = '', memories=None, client=None) -> None:
        self.session = session
        self.style = style   # mode.ConversationStyle
        self.nudge = nudge
        self.correction_nudge = correction_nudge
        self.state_header = state_header   # 心の状態の項目の頭（config/prompts/talk_inner_state.md）
        self.memories = memories   # 今話している人について覚えていること（呼ぶと文字列の一覧。使ってよいときだけ。agent.py がつなぐ）
        self._state_item_id: str | None = None   # 会話の後ろに置いた心の状態の項目
        self._state_text: str | None = None
        self.history = history   # conversation.Conversation（最近の発言）
        self.instructions = instructions
        self._client = client
        self.thoughts: list[Thought] = []
        self.expressed: list[str] = []   # 最近話した考え（繰り返さないため）
        self.unknowns: list[str] = []
        self.topic = ''                  # 今の話題（考える係の解釈）
        self.unanswered = 0              # 話しかけたのに返事が無かった回数
        self._last = time.monotonic()    # 最後に誰かが話していた時刻
        self._user_busy = False
        self._agent_busy = True          # あいさつが終わるまでは話しかけない
        self.paused = None               # 呼ぶと True のあいだ考えも話しかけもしない（声の登録の途中。agent.py がつなぐ）
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
        self.board: board.Board | None = None   # 付箋の一覧（pipeline。つなぐと付箋の形で話す。agent.py がつなぐ）
        self.open_nudge = ''               # 話す番の合図（config/prompts/initiative_open.md）
        self._cards: dict[str, board.Card] = {}   # 考えの id → 気になっている付箋
        self.curious = None                # curiosity.Curiosity（調べてみたいことを自分で調べる。agent.py がつなぐ）

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

    def interlude(self) -> None:
        """長い間（歌を聴いていた）のあと。それまでの考えは古い（歌う前の「これから歌ってくれる」など）ので捨て、
        静けさを今から数え直す。歌っているあいだは会話モデルに声が届かず、ずっと静かだったことになっていて、
        歌い終わった瞬間に、歌う前の考えを話しかけていた（2026-10-27、「これから歌い始める」と取り違えた）"""
        self.thoughts = []   # 知りたいこと（unknowns）は歌と関係がないので残す
        self.unanswered = 0
        self._last = time.monotonic()
        self._spoke_at = None
        self._agent_done_at = None
        self._new_at = None

    def busy(self) -> bool:
        """だれかが話しているか、シエルが返事を考えている・話している最中か（議事録の送った結果を伝える切れ目を見る）"""
        return self._user_busy or self._agent_busy

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
        if self.paused is not None and self.paused():
            return   # 声の登録の途中など、シエルから話しかけない間（agent.py がつなぐ）
        talk = self.style.talk
        if talk == 'quiet':
            if self.board is not None:
                self._cards = self._clear_cards()
            return
        self._watch_history(now)
        if self._should_think(now):
            self._thought_at = now
            self._thinking = asyncio.create_task(self._think(now))
        if self.board is not None:
            self.sync_board(now)
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
        # 相手が話し続けているあいだ（文字起こしが一言ずつ確定する）は、最後に声がしてから待つ。
        # 「ねえ、シエル。」だけで考え始めると、その一言に反応した考えができる
        if (self._new_at is not None and not self._user_busy
                and now - max(self._new_at, self._last) >= THINK_SETTLE_SECONDS):
            return True
        # 静かなあいだにも考える（おしゃべりのときだけ。返事が無いほど間をあける）
        idle = min(IDLE_THINK_SECONDS * 2 ** self.unanswered, IDLE_THINK_MAX)
        return (self.style.talk == 'chatty' and not self._user_busy and not self._agent_busy
                and now - self._last >= idle and now - self._thought_at >= idle)

    def score(self, t: Thought, now: float) -> float:
        """話したい気持ちの今の強さ：静かなほど少し上がり、古いほど下がり、話したばかりなら下がる（満腹度）。
        付箋の形では、静けさと満腹度を使わない（古いほど下がるだけ）"""
        loss = STALE_LOSS * max(0.0, (now - t.created) - STALE_SECONDS) / STALE_SECONDS
        if self.board is not None:
            return t.motivation - loss
        silence = max(0.0, now - self._last)
        gain = min(SILENCE_GAIN * int(silence // SILENCE_STEP), SILENCE_GAIN_MAX)
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

    def turns_since(self, anchor: int) -> int:
        """きっかけの発言のあとに、相手が話した回数"""
        if self.history is None:
            return 0
        return sum(1 for t in self.history.between(anchor) if t.role == 'user' and t.text)

    def alive(self, t: Thought, now: float) -> bool:
        """まだ話す意味がある考えか（話した・時間がたちすぎた・反応した発言から会話が進みすぎた、なら用済み）"""
        return (not t.expressed and now - t.created < DROP_SECONDS
                and not (t.kind in REACTIVE_KINDS and self.turns_since(t.anchor) >= REACTIVE_TURNS))

    def pick(self, now: float) -> Thought | None:
        """今話す考え（無ければ None）"""
        self.thoughts = [t for t in self.thoughts if self.alive(t, now)]
        if self.board is not None:
            return self._pick_open(now)
        candidates = [t for t in self.thoughts if not t.offered]   # 心の状態に載せた考えは、話したか分かるまで待つ
        silence = now - self._last
        talk = self.style.talk
        if talk == 'chatty':
            if silence >= FALLBACK_SECONDS:
                threshold = THRESHOLD
            elif self.continuing(now):
                # 続けて話すのは、とても話したいことだけ（気持ち 4 の考えは、心の状態として次の返事に混ぜる）
                threshold = CONTINUE_THRESHOLD
            else:
                return None
            best = max(candidates, key=lambda t: self.score(t, now), default=None)
            return best if best is not None and self.score(best, now) >= threshold else None
        if talk == 'normal' and silence >= CORRECTION_PAUSE_SECONDS:
            return next((t for t in candidates if t.kind == 'correction' and t.motivation >= 5), None)
        return None

    def _pick_open(self, now: float) -> Thought | None:
        """付箋の形：話す番が来て、気になっている付箋があれば、そのいちばん強い考え（話すかは心が決める）"""
        talk = self.style.talk
        if talk == 'normal' and now - self._last >= CORRECTION_PAUSE_SECONDS:
            fix = next((t for t in self.thoughts if t.kind == 'correction' and t.motivation >= 5), None)
            if fix is not None:
                return fix
        shown = [t for t in self.thoughts if t.id in self._cards]
        if self.continuing(now):
            return max(shown, key=lambda t: self.score(t, now), default=None)
        if talk == 'chatty' and self._spoke_at is None:
            # 静かなあいだに、強い考えが新しく浮かんだ（時間ではなく出来事で話す）
            new = [t for t in shown if t.created > self._last and t.motivation >= CONTINUE_THRESHOLD]
            return max(new, key=lambda t: t.motivation, default=None)
        return None

    def board_thoughts(self, now: float) -> list[Thought]:
        """付箋にする考え：今の話題に新しく（きっかけの発言のあと相手が話したのは 1 回まで）、気持ちが基準を超えたもの。
        言い直しは付箋にせず、すぐ話す"""
        return sorted((t for t in self.thoughts if self.alive(t, now) and t.kind != 'correction' and not t.researching
                       and self.turns_since(t.anchor) <= 1 and self.score(t, now) >= THRESHOLD),
                      key=lambda t: -self.score(t, now))[:BOARD_THOUGHTS]

    def _clear_cards(self) -> dict:
        """気になっている付箋を全部外す（ひかえめのあいだは、自分から話題にしない）"""
        for card in self._cards.values():
            self.board.remove(card)
        return {}

    def sync_board(self, now: float) -> None:
        """気になっている付箋を、今の考えに合わせる。付箋にした考えは「見せた」にして、話したかを次に考えるときに確かめる"""
        if self.curious is not None:
            for t in self.thoughts:
                if t.kind == 'research' and t.query and not t.researching and self.alive(t, now):
                    self.curious.offer(t)   # 受けたら researching になり、気になっている付箋からは外れる
        want = {t.id: t for t in self.board_thoughts(now)}
        for tid in [tid for tid in self._cards if tid not in want]:
            self.board.remove(self._cards.pop(tid))
        last_id = self.history.last_id if self.history is not None else 0
        for t in want.values():
            if t.id not in self._cards:
                self._cards[t.id] = self.board.add('thought', f'{t.text}（{KIND_LABELS[t.kind]}）', board.WANT, 'self',
                                                   ref=t.id)
            if not t.offered:
                t.offered, t.shown_id = True, last_id

    def state_note(self) -> str | None:
        """会話の後ろに置く、シエルの今の心の状態（turns.py が返事を頼むときに呼ぶ）。前に置いたものと同じなら None。
        「言えたら添えて」という用事として渡すと、会話モデルは目の前の返事を優先してほとんど使わなかった（2026-10-24）。
        気持ちとして置いておき、流れに合うときに自然に使わせる。載せるのは今の話題に新しく、気持ち − 満腹度が基準を
        超えた考えだけ（満腹度が高いほど少なく、満ちていれば載せない）"""
        if self.style.talk != 'chatty' or not self.state_header or self.board is not None:
            return None   # 付箋の形では、気になっていることは付箋の一覧で渡す
        now = time.monotonic()
        satiety = self.satiety_at(now)
        if satiety >= 1.5:
            drive, limit = '自分から話したばかりで満ちている。今は相手の話を聞きたい', 0
        elif satiety >= 0.5:
            drive, limit = 'すこし満たされている', 1
        else:
            drive, limit = 'ふつう', 2
        # 今の話題に新しい考えだけ：きっかけの発言のあと、相手が話したのは今答えようとしている 1 回だけ
        fresh = sorted((t for t in self.thoughts if self.alive(t, now) and t.kind != 'correction'
                        and self.turns_since(t.anchor) <= 1 and self.score(t, now) >= THRESHOLD),
                       key=lambda t: -self.score(t, now))[:limit]
        last_id = self.history.last_id if self.history is not None else 0
        for t in fresh:
            if not t.offered:
                t.offered, t.shown_id = True, last_id   # 見せた。話したかは、次に考えるときに確かめる（apply の spoken）
        lines = [self.state_header,
                 'いま気になっていること：' + ('、'.join(f'{t.text}（{KIND_LABELS[t.kind]}）' for t in fresh) or '特になし'),
                 *(['知りたいこと：' + '、'.join(self.unknowns[:3])] if self.unknowns and limit else []),
                 '話したい気持ち：' + drive]
        note = '\n'.join(lines)
        if note == self._state_text:
            return None
        log.info('内なる考え：心の状態を置く（気になっていること %d 個、満腹度 %.1f）', len(fresh), satiety)
        debug_log.record('inner_state', text=note)
        return note

    async def place_state(self, note: str) -> bool:
        """心の状態を会話の後ろに system の項目として置く（前に置いた項目は消して置き換える）。置けなければ False
        （呼んだ側が、今回の返事の指示に足す）。置いたと確かめる返事は待たない（turns.py の _add_context と同じ）"""
        agent = getattr(self.session, 'current_agent', None)
        if agent is None:
            return False
        try:
            ctx = agent.chat_ctx.copy()
            remote = getattr(agent, 'realtime_llm_session', None)
            local_ids = {item.id for item in ctx.items}
            if remote is not None and any(item.id not in local_ids for item in remote.chat_ctx.items):
                return False   # 会話モデルの側にだけある項目（まだ手元に届いていない発言）を消してしまうので、置かない
            if self._state_item_id is not None:
                ctx.items[:] = [item for item in ctx.items if item.id != self._state_item_id]
            message = ctx.add_message(role='system', content=note)
        except Exception as e:
            log.warning('心の状態を会話に置けない（返事ごとの指示に足す）: %s', type(e).__name__)
            return False
        task = asyncio.create_task(agent.update_chat_ctx(ctx))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        await asyncio.sleep(0)   # 項目を作る知らせを送るところまで進める
        if task.done() and not task.cancelled() and task.exception() is not None:
            return False
        self._state_item_id, self._state_text = message.id, note
        return True

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
        self.thoughts.append(Thought(text, kind if kind in KINDS and kind != 'correction' else 'question', 4.0,
                                     anchor=self.history.settled_through() if self.history is not None else 0))
        self.thoughts = sorted(self.thoughts, key=lambda t: -t.motivation)[:MAX_THOUGHTS]
        log.info('内なる考え：会話モデルが考えを預けた（%s）', kind)
        debug_log.record('thought_kept', thought_kind=kind, text=text)
        return 'kept'

    def _express(self, t: Thought, now: float) -> None:
        self._agent_done_at = None   # 続けて話すのは 1 回だけ
        if self.board is not None and t.kind != 'correction':
            # 付箋の形：どの付箋を話すか・黙るかは心が決める。話したかは、次に考えるときに確かめる
            self._spoke_at = self._last = now
            log.info('内なる考え：話す番。心に話すかを決めさせる（気になっていること %d 個、いちばん強い気持ち %.0f）',
                     len(self._cards), t.motivation)
            debug_log.record('thought_opening', thought_kind=t.kind, text=t.text, motivation=t.motivation)
            self._reply(self.open_nudge or self.nudge, '', placed=True)
            return
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
        if getattr(self.session, 'current_agent', None) is None or self.board is not None:
            # 付箋の形（pipeline）では、LiveKit の会話を書き換えない（mind.py が今回の分から文脈を作る）
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
            mouth.of(self.session).say('initiative', instructions=nudge if placed else f'{nudge}\n\n{note}')
        except Exception as e:   # 話しかけられなくても、会話は続ける
            log.warning('話しかけられない: %s', e)

    # ---- 考える ----

    def _memories(self) -> list[str]:
        """今話している人について覚えていること（使ってよいときだけ。agent.py の memories）"""
        if self.memories is None:
            return []
        try:
            return [m.strip()[:200] for m in self.memories() if isinstance(m, str) and m.strip()][:15]
        except Exception as e:
            log.warning('内なる考え：覚えていることを読めない: %s', type(e).__name__)
            return []

    def _ciel_since(self, after: int) -> list[str]:
        """心の状態に載せたあとのシエルの発言（載せた考えを話したかは、これだけで判定させる）"""
        if self.history is None:
            return []
        return [t.text[:400] for t in self.history.between(after) if t.role == 'assistant' and t.text]

    def _conversation(self) -> list[dict]:
        if self.history is None:
            return []
        rows = [t for t in self.history.between(through=self.history.settled_through()) if t.text][-CONVERSATION_TURNS:]
        # 同じ人の続けての発言は 1 つにつなぐ（文字起こしは「でも、」「寒くて…」のように切れて届き、切れ端に反応した
        # 考え（「『でも、』の続きが気になる」）ができた。2026-10-24）
        lines: list[dict] = []
        for t in rows:
            if lines and lines[-1]['speaker'] == t.name:
                lines[-1]['text'] = (lines[-1]['text'] + t.text)[:800]
            else:
                lines.append({'speaker': t.name, 'text': t.text[:400]})
        return lines

    async def _think(self, now: float) -> None:
        if self.history is not None:
            self._seen_id = self.history.settled_through()
        self._new_at = None
        self.thoughts = [t for t in self.thoughts if self.alive(t, now)]
        sent = list(self.thoughts)
        memories = self._memories()
        wall = datetime.now(JST)
        request = {
            'now': f'{wall:%Y-%m-%d %H:%M}（{"月火水木金土日"[wall.weekday()]}）',
            'talk': self.style.talk,
            'silence_seconds': round(max(0.0, now - self._last)),
            'conversation': self._conversation(),
            'thoughts': [{'id': t.id, 'text': t.text, 'kind': t.kind, 'motivation': t.motivation,
                          **({'offered': True} if t.offered else {})} for t in sent],
            'expressed': self.expressed,
            'unknowns': self.unknowns,
            **({'topic': self.topic} if self.topic else {}),
            **({'memories': memories} if memories else {}),
            **({'ciel_since_shown': self._ciel_since(min(t.shown_id for t in sent if t.offered))}
               if any(t.offered for t in sent) else {}),
        }
        try:
            r = await self.client.chat.completions.create(
                model=MODEL, reasoning_effort='low', response_format={'type': 'json_object'}, timeout=THINK_TIMEOUT,
                messages=[{'role': 'system', 'content': self.instructions},
                          {'role': 'user', 'content': json.dumps(request, ensure_ascii=False)}])
            models.record('thought', MODEL, getattr(r, 'usage', None))
            result = json.loads(r.choices[0].message.content or '{}')
        except Exception as e:   # 考えられなくても、会話は続ける
            log.warning('内なる考え：考えられない：%s', type(e).__name__)
            return
        self.apply(result, time.monotonic(), reviewed={t.id for t in sent})

    def apply(self, result, now: float, reviewed: set[str] | None = None) -> None:
        """モデルの答え（config/prompts/inner_thoughts.md の形）を、貯めている考えに当てる。
        reviewed は、見直しを頼んだ前の考えの id（付け直しも捨てもされなかったものは、気持ちを下げる）"""
        if not isinstance(result, dict):
            return
        anchor = self._seen_id
        by_id = {t.id: t for t in self.thoughts}
        # 心の状態に載せた考えを、シエルが実際に話したか（話していれば満腹度を上げる。話していなければ気持ちを下げる）
        spoken = _ids(result.get('spoken'))
        # 相手の発言で答えが出た考え（聞きたいこと・戻りたいこと）は捨てる。もう答えた質問が残り、
        # 話題に出ることがあった（2026-10-24、評価の AI の動向の場面）
        answered = _ids(result.get('answered')) - spoken
        dropped = _ids(result.get('drop')) | answered
        if answered & set(by_id):
            log.info('内なる考え：答えが出た考えを捨てた（%d 個）', len(answered & set(by_id)))
        for t in list(self.thoughts):
            # 載せたあと、シエルがまだ話していなければ、判定は保留（載せる前の発言で「話した」にしない）
            pending = t.offered and self.history is not None and not self._ciel_since(t.shown_id)
            if t.id in spoken and not pending:
                t.expressed = True
                self.expressed = (self.expressed + [t.text])[-8:]
                if t.offered:
                    self._sate(now, SATE_SPEAK)
                    log.info('内なる考え：心の状態に載せた考えを話した（%s）', t.kind)
                    debug_log.record('thought_spoken', thought_kind=t.kind, text=t.text)
                self.thoughts.remove(t)
                by_id.pop(t.id, None)
            elif t.offered and not pending:
                t.offered = False
                t.motivation = max(1.0, t.motivation - UNUSED_OFFER_LOSS)
        for d in dropped:
            if d in by_id:
                self.thoughts.remove(by_id.pop(d))
        touched = spoken | dropped
        for r in result.get('rescore') or []:
            if isinstance(r, dict) and r.get('id') in by_id:
                t = by_id[r['id']]
                t.motivation = _motivation(r.get('motivation'), t.motivation)
                t.anchor = anchor   # 今の会話で見直された：きっかけを今に付け直す
                touched.add(t.id)
        for t in self.thoughts:
            if reviewed and t.id in reviewed and t.id not in touched:
                t.motivation = max(1.0, t.motivation - UNREVIEWED_LOSS)   # 見直されずに放っておかれた考えは沈める
        # 相手の最新の発言の解釈（研究 Inner Thoughts の「考える前に解釈する」）。話題が移ったら、前の話題への反応は用済み、
        # 前の話題の聞きたいこと・戻りたいことは気持ちを下げる。あいさつ・言いかけの切れ端からは新しい考えを作らない
        interpretation = result.get('interpretation') if isinstance(result.get('interpretation'), dict) else {}
        content = interpretation.get('content')
        topic = interpretation.get('topic').strip()[:40] if isinstance(interpretation.get('topic'), str) else ''
        if interpretation.get('topic_shift') is True and topic:
            for t in list(self.thoughts):
                if t.topic and t.topic != topic and t.id not in touched:
                    if t.kind in REACTIVE_KINDS:
                        self.thoughts.remove(t)
                    else:
                        t.motivation = max(1.0, t.motivation - TOPIC_SHIFT_LOSS)
        if topic:
            self.topic = topic
        added = 0
        for raw in result.get('thoughts') or []:
            if added >= 3 or content in ('greeting', 'fragment'):
                break
            if not isinstance(raw, dict) or not isinstance(raw.get('text'), str) or not raw['text'].strip():
                continue
            stimulus = raw.get('stimulus').strip()[:120] if isinstance(raw.get('stimulus'), str) else ''
            if not stimulus:
                continue   # きっかけを言えない考えは作らない（漠然とした考えを防ぐ）
            text = raw['text'].strip()[:80]
            if any(t.text == text for t in self.thoughts) or text in self.expressed:
                continue
            kind = raw.get('kind') if raw.get('kind') in KINDS else 'comment'
            query = raw.get('query').strip()[:200] if kind == 'research' and isinstance(raw.get('query'), str) else ''
            self.thoughts.append(Thought(text, kind, _motivation(raw.get('motivation'), 1.0), created=now, anchor=anchor,
                                         topic=self.topic, stimulus=stimulus, query=query))
            added += 1
        # 同じ話題・同じ種類の考えは、気持ちの強いものから PER_TOPIC_KIND 個まで（言い方を変えただけの似た考えが
        # 積み重なった。2026-10-24、評価の AI の動向の場面）
        kept, count = [], {}
        for t in sorted(self.thoughts, key=lambda t: -t.motivation):
            key = (t.topic, t.kind)
            if t.topic and count.get(key, 0) >= PER_TOPIC_KIND:
                continue
            count[key] = count.get(key, 0) + 1
            kept.append(t)
        self.thoughts = kept[:MAX_THOUGHTS]
        unknowns = result.get('unknowns')
        if isinstance(unknowns, list):
            self.unknowns = [u.strip()[:60] for u in unknowns if isinstance(u, str) and u.strip()][:8]
        top = max((t.motivation for t in self.thoughts), default=0)
        log.info('内なる考え：%d 個足した（貯めている %d 個、いちばん強い気持ち %.0f、知りたいこと %d 個）',
                 added, len(self.thoughts), top, len(self.unknowns))
        debug_log.record('thoughts', thoughts=[{'text': t.text, 'kind': t.kind, 'motivation': t.motivation,
                                                 'stimulus': t.stimulus} for t in self.thoughts],
                         unknowns=self.unknowns, interpretation=interpretation)


def _ids(value) -> set[str]:
    """考えの id の一覧。モデルは文字列のほかに {"id": …} で返すこともある（2026-10-24、評価で見つけた）"""
    if not isinstance(value, list):
        return set()
    return {v if isinstance(v, str) else v.get('id') for v in value
            if isinstance(v, str) or (isinstance(v, dict) and isinstance(v.get('id'), str))}


def _motivation(value, default: float) -> float:
    try:
        return max(1.0, min(5.0, float(value)))
    except (TypeError, ValueError):
        return default
