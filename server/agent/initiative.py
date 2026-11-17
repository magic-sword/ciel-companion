"""Consider a changed conversation once at a quiet moment, using the normal reply prefix."""
import asyncio
import collections
import inspect
import time

import debug_log


class Initiative:
    POLL = .5
    QUIET = 8.0
    COOLDOWN = 30.0

    def __init__(self, history, mouth, decider, template, trigger, *, allowed=lambda: True, clock=time.monotonic, observe=lambda **state: None):
        self.history, self.mouth, self.decider = history, mouth, decider
        self.template, self.trigger, self.allowed, self.clock = template, trigger, allowed, clock
        self.counts = collections.Counter()
        self._consumed = 0
        self._observed = None
        self._changed = clock()
        self._last = -float('inf')
        self._generation = 0
        self._pending = None
        self._considered = None
        self._handle = None
        self._request_task = self._decision_task = self._loop = None
        self._closed = False
        self._opening = 0
        self.observe = observe
        self._outcome = ''

    def show(self, phase, reason=''):
        self.observe(phase=phase, reason=reason, outcome=self._outcome)

    def snapshot(self):
        rows = [t for t in self.history.turns if t.ready.is_set() and t.text]
        # An autonomous reply cannot be its own reason to think again.
        external = max((t.id for t in rows if t.role in ('user', 'event')), default=0)
        if not external and not self._opening:
            self._opening = next((t.id for t in rows if t.role == 'assistant'), 0)
        external = external or self._opening
        return external, max((t.id for t in rows), default=0)

    def trigger_allowed(self):
        latest = next((t for t in reversed(self.history.turns)
                       if t.ready.is_set() and t.text and t.role in ('user', 'event')), None)
        return bool(self._opening) if latest is None else (
            latest.role == 'user' and not latest.label.startswith('コメント・')
            or latest.role == 'event' and latest.label in ('game', 'work', 'research', 'image'))

    def record(self, status, **fields):
        self.counts[status] += 1
        debug_log.record('initiative', status=status, **fields)

    def on_user_state(self, event):
        if event.new_state == 'speaking':
            self._generation += 1
            self._changed = self.clock()
            if self._pending is not None:
                self.record('interrupted', overlap=getattr(self.mouth.session, 'agent_state', None) == 'speaking')
                if self._decision_task is not None:
                    self._decision_task.cancel()
                if self._handle is not None:
                    self._handle.interrupt(force=True)

    def valid(self, token):
        return (not self._closed and token == self._pending and token[1] == self._generation
                and token[0] == self.snapshot()[0] and self.allowed() and self.trigger_allowed()
                and getattr(self.mouth.session, 'user_state', None) != 'speaking')

    def step(self):
        now, snapshot = self.clock(), self.snapshot()
        if snapshot != self._observed:
            self._observed, self._changed = snapshot, now
        if self._closed:
            self.show('disabled', 'closed')
            return
        busy, allowed = self.mouth.busy(), self.allowed()
        if busy or not allowed:
            self._changed = now
        if self._request_task is not None and not self._request_task.done():
            return
        if busy or not allowed:
            self.show('waiting', 'conversation' if busy else 'mode')
            return
        if snapshot[0] <= self._consumed:
            self.show('waiting', 'new_event')
            return
        if now - self._changed < self.QUIET:
            self.show('waiting', 'quiet')
            return
        if now - self._last < self.COOLDOWN:
            self.show('waiting', 'cooldown')
            return
        if not self.trigger_allowed():
            self._consumed = snapshot[0]
            self.show('waiting', 'eligible_event')
            return
        self._consumed, self._last = snapshot[0], now
        self._pending = (snapshot[0], self._generation)
        self.record('scheduled', through=snapshot[0])
        self.show('scheduled')
        self._request_task = asyncio.create_task(self._request(self._pending))

    async def _request(self, token):
        try:
            if not self.valid(token):
                return
            self._handle = self.mouth.say('initiative', instructions=self.trigger, tool_choice='none')
            if inspect.isawaitable(self._handle):
                await self._handle
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.record('error', error=type(error).__name__)
            self._outcome = 'error'
        finally:
            self._pending = self._handle = None
            self.show('waiting', 'new_event')

    async def reply(self, messages, tools, game=''):
        token = self._pending
        if token is None or token == self._considered or not self.valid(token):
            return ''
        self._considered = token
        self._decision_task = asyncio.current_task()
        began = self.clock()
        self.show('deciding')
        try:
            result = await self.decider.consider(messages, tools, self.template, game=game,
                                                 valid=lambda: self.valid(token))
            self.record(result['status'], through=token[0], seconds=round(self.clock()-began, 3),
                        acted=result['acted'], speaks=bool(result['say']))
            self._outcome = {'spoken': 'spoke', 'failed': 'error'}.get(result['status'], result['status'])
            self.show('waiting', 'new_event')
            return result['say'] if self.valid(token) else ''
        except asyncio.CancelledError:
            self._outcome = 'cancelled'
            self.show('waiting', 'conversation')
            self.record('cancelled', through=token[0], seconds=round(self.clock()-began, 3), speaks=False)
            raise
        finally:
            self._decision_task = None

    def start(self):
        self._loop = asyncio.create_task(self._run())

    async def _run(self):
        while not self._closed:
            self.step()
            await asyncio.sleep(self.POLL)

    async def close(self):
        self._closed = True
        if self._handle is not None:
            self._handle.interrupt(force=True)
        tasks = [t for t in (self._loop, self._request_task, self._decision_task) if t is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.show('disabled', 'closed')
        debug_log.record('initiative_summary', counts=dict(self.counts))
