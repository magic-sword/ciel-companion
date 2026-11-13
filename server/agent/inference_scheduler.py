"""CIEL-side admission for concurrent inference from external clients (games, tools).

Clients may send requests concurrently, as with ordinary hosted LLM APIs. The host decides
how many run at once and in which order; clients never serialize on their own. The shared
local model's slots are also used by Ciel's own conversation, so external work is limited
to `slots` and the rest waits by priority (decisions before background summaries), then
arrival. A later stage can route overflow to another backend from here.
"""
import asyncio
import contextlib
import heapq
import itertools
import os
import time

PRIORITY = {'decision': 0, 'background': 1}


class InferenceScheduler:
    def __init__(self, slots=1):
        if not isinstance(slots, int) or slots < 1:
            raise ValueError('Inference slots must be a positive integer')
        self.slots = slots
        self.active = 0
        self.waiting = []
        self.order = itertools.count()

    @contextlib.asynccontextmanager
    async def slot(self, priority='decision'):
        """Hold one slot for the body; yields how long the request waited."""
        if priority not in PRIORITY:
            raise ValueError('Unknown inference priority')
        began = time.monotonic()
        if self.active < self.slots:
            self.active += 1
        else:
            granted = asyncio.get_running_loop().create_future()
            entry = (PRIORITY[priority], next(self.order), granted)
            heapq.heappush(self.waiting, entry)
            try:
                await granted
            except asyncio.CancelledError:
                if granted.done() and not granted.cancelled():
                    self._release()  # Granted at the same moment as cancellation: hand it on.
                else:
                    # Keep the invariant "someone waits only while every slot is held".
                    with contextlib.suppress(ValueError):
                        self.waiting.remove(entry)
                        heapq.heapify(self.waiting)
                raise
        try:
            yield round(time.monotonic() - began, 3)
        finally:
            self._release()

    def _release(self):
        while self.waiting:
            *_, granted = heapq.heappop(self.waiting)
            # A waiter cancelled but not yet resumed is already done; skip it.
            if not granted.done():
                granted.set_result(None)  # The slot passes directly to the next waiter.
                return
        self.active -= 1

    def status(self):
        return {'slots': self.slots, 'active': self.active, 'waiting': len(self.waiting)}


_shared = None


def shared():
    """One scheduler per agent process, shared by every bound core session."""
    global _shared
    if _shared is None:
        _shared = InferenceScheduler(int(os.environ.get('CIEL_CORE_INFERENCE_SLOTS', '1')))
    return _shared
