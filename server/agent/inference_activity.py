"""Per-job foreground priority for optional local inference.

Callers retain their pending work on Deferred and retry on their next event.
Only the model request is interrupted; database writes are never cancelled here.

Two gates:
- available(): nobody is speaking or thinking, for 3 seconds (notes, summaries, keys).
- available_while_speaking(): the owner is not speaking and no reply is being generated, for a short
  moment. Ciel may still be speaking: the reply's text is complete, so the model is idle while the
  voice plays. Used by the mind's recall (recall.MindRecall) so that it can finish before the next turn.
"""
import asyncio
import contextlib
import time

SPEAKING_GRACE = 0.5   # 返事を作り終えて（相手が話し終えて）から、話している間の推論を送るまでの間


class Deferred(RuntimeError):
    pass


class Activity:
    def __init__(self):
        self.user = self.agent = False
        self.quiet_since = -1e9
        self.generating = 0          # 作っている途中の返事の数（agent.llm_node）
        self.generated_at = -1e9     # 最後に返事を作り終えた／相手が話し終えた時刻
        self.requests = set()
        self.speaking_requests = set()

    def update(self, *, user=None, agent=None):
        if user is not None:
            self.user = user
            if not user:
                self.generated_at = time.monotonic()
        if agent is not None:
            self.agent = agent
        self.quiet_since = time.monotonic()
        if self.user or self.agent:
            for task in tuple(self.requests):
                task.cancel()
        if self.user:
            for task in tuple(self.speaking_requests):
                task.cancel()

    @contextlib.contextmanager
    def replying(self):
        """返事を作っている間（話している間の推論は取り消し、新しく送らない）"""
        self.generating += 1
        for task in tuple(self.speaking_requests):
            task.cancel()
        try:
            yield
        finally:
            self.generating -= 1
            self.generated_at = time.monotonic()

    def available(self):
        return not (self.user or self.agent) and time.monotonic() - self.quiet_since >= 3

    def available_while_speaking(self):
        return not self.user and self.generating == 0 and time.monotonic() - self.generated_at >= SPEAKING_GRACE

    async def run(self, operation, *, while_speaking=False, **kwargs):
        if not (self.available_while_speaking() if while_speaking else self.available()):
            raise Deferred('Foreground conversation has priority')
        task = asyncio.create_task(operation(**kwargs))
        requests = self.speaking_requests if while_speaking else self.requests
        requests.add(task)
        try:
            return await task
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
            raise Deferred('Foreground conversation interrupted background inference') from None
        finally:
            requests.discard(task)


activity = Activity()
