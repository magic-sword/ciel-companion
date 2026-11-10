"""Per-job foreground priority for optional local inference.

Callers retain their pending work on Deferred and retry on their next event.
Only the model request is interrupted; database writes are never cancelled here.
"""
import asyncio
import time


class Deferred(RuntimeError):
    pass


class Activity:
    def __init__(self):
        self.user = self.agent = False
        self.quiet_since = -1e9
        self.requests = set()

    def update(self, *, user=None, agent=None):
        if user is not None:
            self.user = user
        if agent is not None:
            self.agent = agent
        self.quiet_since = time.monotonic()
        if self.user or self.agent:
            for task in tuple(self.requests):
                task.cancel()

    def available(self):
        return not (self.user or self.agent) and time.monotonic() - self.quiet_since >= 3

    async def run(self, operation, **kwargs):
        if not self.available():
            raise Deferred('Foreground conversation has priority')
        task = asyncio.create_task(operation(**kwargs))
        self.requests.add(task)
        try:
            return await task
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
            raise Deferred('Foreground conversation interrupted background inference') from None
        finally:
            self.requests.discard(task)


activity = Activity()
