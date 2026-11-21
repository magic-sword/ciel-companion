# -*- coding: utf-8 -*-
"""話す番で、自分から話す（docs/conversation/speaking-motivation-ja.md の段階3）。

心の見極め（recall.MindRecall）は、シエルの返事 N を読んでから、相手の発言 N について話したいことを考える。
「高い」考え（点が HIGH より上）が出たら、その考えを話す返事を口に頼み（mouth.say('idea')）、言葉ができたらそのまま
話す（hold）。沈黙の長さは決めない：考えが終われば話し出すのが、自分で考えて話す振る舞いとして自然（2026-11-21
利用者が決めた）。返事 N をまだ話していれば、その後に続ける。相手と重なったら、今の割り込みの仕組みが読み上げを止める。
話し出す前に相手が次の発言を始めたら、考えは前の発言についてのものなので捨てる。

- 推論は増やさない：考えと点は、相手の発言ごとの心の 1 回で出ている。ここは話す言葉を 1 回作るだけで、時間では考え直さない。
- 新しさ：返事 N と 2 字組が REPEAT 以上重なる考えは話さない（返事で答えたことを繰り返さない）。
- 釣り合い：自分から話したあと ANSWER 秒の間に相手が話さなければ、次に話す基準を上げる。相手が答えたら戻す。
- 場：おしゃべり度がふつうかおしゃべりのときだけ（allowed）。その場の人（ひとり・親しい人・人前）は問わない。
"""
from __future__ import annotations

import asyncio
import time

import debug_log


def bigrams(text: str) -> set[str]:
    t = ''.join(ch for ch in text if ch.isalnum())
    return {t[i:i + 2] for i in range(len(t) - 1)}


def overlap(idea: str, said: str) -> float:
    """考えの 2 字組のうち、言ったことに入っている割合"""
    a = bigrams(idea)
    return len(a & bigrams(said)) / len(a) if a else 0.0


class SpeakUp:
    POLL = 0.25
    HIGH = 3.5            # これより上（高い・とても高い）の考えだけ、自分から話す
    WAIT = 20.0           # 声にする番を待つ上限
    REPEAT = 0.3          # 返事とこれ以上重なる考えは話さない
    ANSWER = 15.0         # 自分から話したあと、これだけの間に相手が話せば「答えた」
    STEP = 0.5            # 答えが無かったときに上げる基準

    def __init__(self, session, mouth, mind_recall, history, template: str, *, allowed=lambda: True,
                 clock=time.monotonic) -> None:
        self.session, self.mouth, self.mind_recall, self.history = session, mouth, mind_recall, history
        self.template, self.allowed, self.clock = template, allowed, clock
        self.handle = None            # 頼んだ、自分から話す返事（声になるか捨てるまで）
        self.reply = None             # 今話している（直前に話した）返事 N
        self.reply_ended: float | None = None
        self.reply_text = ''          # 返事 N の文（新しさを見る）
        self.unanswered = 0
        self.spoken_at: float | None = None
        self._user_seen = 0
        self._task: asyncio.Task | None = None
        self._user_spoke = asyncio.Event()
        self.view = None              # mind_view.MindView（話した・落とした、をアプリへ見せる）
        self._turn: int | None = None # 頼んだ考えの発言

    # ---- 会話から知らせる ----

    def on_user_state(self, ev) -> None:
        if getattr(ev, 'new_state', None) == 'speaking':
            self._user_spoke.set()
            if self.handle is not None and not getattr(self.handle, 'done', lambda: True)():
                debug_log.record('speak_up', status='aborted', reason='user_spoke')
                self._show('aborted', 'user_spoke')
                self.handle.interrupt(force=True)
                self.handle = None

    def replied(self, text: str) -> None:
        """返事を作り終えた（agent._pipeline_llm）。自分から話す返事の文は数えない"""
        if text.strip():
            self.reply_text = text

    def _show(self, status: str, reason: str = '', turn: int | None = None) -> None:
        if self.view is not None:
            self.view.outcome(self._turn if turn is None else turn, status, reason, self.threshold)

    @property
    def threshold(self) -> float:
        return self.HIGH + self.STEP * self.unanswered

    # ---- 頼む ----

    def _latest_user(self):
        return next((t for t in reversed(self.history.turns) if t.role == 'user' and t.text and t.ready.is_set()), None)

    def _track(self) -> None:
        current = getattr(self.session, 'current_speech', None)
        if current is not None and current is not self.handle and not current.done():
            if current is not self.reply:
                self.reply, self.reply_ended = current, None
        elif self.reply is not None and self.reply_ended is None:
            self.reply_ended = self.clock()
        latest = self._latest_user()
        if latest is not None and latest.id != self._user_seen:
            self._user_seen = latest.id
            if self.spoken_at is not None:   # 自分から話したあとの、相手の最初の発言
                self.unanswered = 0 if self.clock() - self.spoken_at <= self.ANSWER else self.unanswered + 1
                self.spoken_at = None

    def step(self) -> None:
        self._track()
        if self.handle is not None:
            if getattr(self.handle, 'done', lambda: False)():
                self.handle = None
            return
        ideas = self.mind_recall.ideas
        latest = self._latest_user()
        if not ideas or latest is None:
            return
        fresh = [i for i in ideas if i.turn == latest.id]
        if not fresh:
            return
        best = max(fresh, key=lambda i: i.level)
        drop = None
        if best.level <= self.threshold:
            drop = 'low'
        elif not self.allowed():
            drop = 'mode'
        elif self.reply is None:
            drop = 'no_reply'
        elif getattr(self.session, 'user_state', None) == 'speaking':
            drop = 'user_speaking'
        elif self.reply_ended is None and not self._reply_generated():
            return   # 返事 N を作っている途中。作り終えるのを待つ（新しさを見るのに返事の文が要る）
        elif overlap(best.text, self.reply_text) >= self.REPEAT:
            drop = 'repeat'
        self.mind_recall.ideas = []   # 1 つの発言の考えは 1 回だけ見る
        fields = dict(level=round(best.level, 2), idea_kind=best.kind, text=best.text, turn=best.turn,
                      threshold=self.threshold, overlap=round(overlap(best.text, self.reply_text), 2),
                      reply_playing=self.reply_ended is None, reply=self.reply_text[:120])
        if drop is not None:
            debug_log.record('speak_up', status='dropped', reason=drop, **fields)
            self._show('dropped', drop, best.turn)
            return
        debug_log.record('speak_up', status='scheduled', **fields)
        self._turn = best.turn
        self._show('scheduled')
        self._user_spoke.clear()
        self.handle = self.mouth.say('idea', instructions=self.template.replace('{idea}', best.text),
                                     tool_choice='none')

    def _reply_generated(self) -> bool:
        import inference_activity
        return inference_activity.activity.generating == 0

    # ---- 声にする番 ----

    async def wait_turn(self) -> bool:
        """返事 N を話し終えたら True（話している途中なら、話し終えるまで待つ）。その前に相手が話し始めたら False"""
        deadline = self.clock() + self.WAIT
        while self.clock() < deadline:
            if self._user_spoke.is_set() or getattr(self.session, 'user_state', None) == 'speaking':
                return False
            current = getattr(self.session, 'current_speech', None)
            if not (current is not None and current is not self.handle and not current.done()):
                return True
            await asyncio.sleep(0.05)
        return False

    async def hold(self, source):
        """自分から話す返事の文を作り切ってから、返事 N を話し終えるのを待って流す。相手が先に話し始めたら流さない"""
        began = self.clock()
        chunks = [c async for c in source]
        made = self.clock()
        ok = await self.wait_turn()
        after_end = round(self.clock() - self.reply_ended, 2) if self.reply_ended is not None else None
        debug_log.record('speak_up', status='spoken' if ok else 'aborted', reason=None if ok else 'user_spoke',
                         generate_s=round(made - began, 2), waited_s=round(self.clock() - made, 2),
                         after_reply_s=after_end)
        self._show('spoken' if ok else 'aborted', '' if ok else 'user_spoke')
        if not ok:
            if self.handle is not None:
                self.handle.interrupt(force=True)
                self.handle = None
            return
        self.spoken_at = self.clock()
        for c in chunks:
            yield c

    # ---- 動かす ----

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self.POLL)
            try:
                self.step()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                debug_log.record('speak_up', status='error', error=type(e).__name__)
