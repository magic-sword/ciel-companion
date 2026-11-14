"""Game-independent work client. Plans, steps and repairs belong to the MCP server."""
import asyncio
import json
import math
import time
import uuid

import debug_log

TOPIC = 'ciel.goal'
TERMINAL = frozenset(('succeeded', 'failed', 'cancelled'))
# The work contract's ceiling for one work (the game enforces the same limit).
MAX_SECONDS = 600
ACTIVE = frozenset(('accepted', 'running', 'needs_decision', 'cancelling'))
STATES = ACTIVE | TERMINAL


class GoalRunner:
    def __init__(self, say, publish=None, *, env=None):
        self.say, self.publish, self.env = say, publish, env
        self.work = None
        self.title = ''
        self._lock = asyncio.Lock()
        self._watch = None
        self._deadline = 0
        self._notified = set()
        self._stream_id = uuid.uuid4().hex
        self._display_revision = 1
        self._confirmed_at = 0
        self._unknown = False
        self.presence = lambda: 'solo'
        self.owner_name = lambda: None

    def _tool(self, key):
        return (self.env.profile.get('work') or {}).get(key)

    async def _call(self, key, args):
        if not self.env.linked or not self._tool(key):
            return {'status': 'unavailable'}
        try:
            return await self.env._call(self._tool(key), args, timeout=6)
        except Exception:
            return {'status': 'unavailable'}

    async def start(self, capability, arguments, *, constraints=None, seconds=90, title='', request_id=None):
        async with self._lock:
            if self.work and self.work['state'] not in TERMINAL:
                return {'status': 'busy'}
            if not self.env or (self.env.profile.get('work') or {}).get('version') != 1:
                return {'status': 'error', 'reason': 'work_protocol_mismatch'}
            if type(seconds) not in (int, float) or not 0 < seconds <= MAX_SECONDS:
                return {'status': 'error', 'reason': 'invalid_budget'}
            self._deadline = time.monotonic() + seconds
            self.title = title or capability
            r = await self._call('submit', {'request_id': request_id or uuid.uuid4().hex, 'capability': capability,
                'arguments': arguments, 'constraints': constraints or {}, 'budget_ms': int(seconds * 1000)})
            if not self.valid(r):
                return r if isinstance(r, dict) and r.get('status') else {'status': 'error', 'reason': 'work_protocol_mismatch'}
            self.work = None
            self.accept(r)
            if self._watch:
                self._watch.cancel()
            self._watch = asyncio.create_task(self._poll(r['task_id']))
            return r

    @staticmethod
    def valid(w):
        return (isinstance(w, dict) and type(w.get('version')) is int and w['version'] == 1
                and isinstance(w.get('state'), str) and w['state'] in STATES
                and isinstance(w.get('task_id'), str) and bool(w['task_id']) and isinstance(w.get('session'), str) and bool(w['session'])
                and (w.get('decision') is None or isinstance(w.get('decision'), dict))
                and (w.get('remaining_ms') is None or (type(w['remaining_ms']) in (int, float)
                     and math.isfinite(w['remaining_ms']) and w['remaining_ms'] >= 0))
                and type(w.get('revision')) is int and w['revision'] > 0)

    def accept(self, w):
        if not self.valid(w):
            return False
        if self.work:
            if (w['task_id'] != self.work['task_id'] or w['session'] != self.work['session']
                    or w['revision'] < self.work['revision']):
                return False
            if w['revision'] == self.work['revision']:
                if ({k: v for k, v in w.items() if k != 'remaining_ms'}
                        != {k: v for k, v in self.work.items() if k != 'remaining_ms'}):
                    return False
                self.work = dict(w)
                self._unknown = False
                self._confirmed_at = time.monotonic()
                self._publish()
                return False
            if self.work['state'] in TERMINAL and w['state'] != self.work['state']:
                return False
        self.work = dict(w)
        self._unknown = False
        self._confirmed_at = time.monotonic()
        debug_log.record('work_state', work=w)
        self._publish()
        if w['state'] in TERMINAL or w['state'] == 'needs_decision':
            key = (w['task_id'], w['state'], (w.get('decision') or {}).get('decision_id'))
            if key not in self._notified:
                self._notified.add(key)
                # Inventory/evidence remain in the current-state supplement, not the event timeline.
                fact = {k: w.get(k) for k in ('task_id', 'state', 'message', 'reason', 'decision')}
                self.say('game', settle=0.2, instructions=json.dumps({'work_result': fact, 'title': self.title}, ensure_ascii=False), merge=True)
        return True

    async def _poll(self, task_id):
        try:
            while self.work and self.work['task_id'] == task_id and self.work['state'] not in TERMINAL:
                if time.monotonic() >= self._deadline and self.work['state'] != 'cancelling':
                    await self.stop()
                r = await self._call('status', {'task_id': task_id})
                if not self.valid(r):
                    # Transport loss is not success, failure or a confirmed stop.
                    self._publish(unknown=True)
                elif not self.accept(r) and r != self.work:
                    self._publish(unknown=True)
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            pass

    async def stop(self, **_):
        if not self.work:
            return {'status': 'no_task'}
        r = await self._call('cancel', {'task_id': self.work['task_id']})
        if not self.accept(r) and r != self.work:
            self._publish(unknown=True)
        return r

    async def answer(self, decision_id, action):
        if not self.work:
            return {'status': 'no_task'}
        if (self.work['state'] != 'needs_decision' or action not in ('retry', 'cancel')
                or decision_id != (self.work.get('decision') or {}).get('decision_id')):
            return {'status': 'error', 'reason': 'stale_decision'}
        r = await self._call('answer', {'task_id': self.work['task_id'], 'decision_id': decision_id, 'action': action})
        if not self.accept(r) and r != self.work:
            self._publish(unknown=True)
        return r

    def body_step(self):
        return self.title if self.work and self.work['state'] in ACTIVE else None

    def context(self):
        return '[今の作業] ' + json.dumps({'title': self.title, 'work': self.work}, ensure_ascii=False) if self.work else None

    def status(self):
        return self.work or {'status': 'no_task'}

    def state(self, unknown=False):
        if unknown:
            self._unknown = True
        w = self.work
        age = max(0, time.monotonic() - self._confirmed_at) if w else 0
        confirmed = not self._unknown and (not w or age < 10)
        task = None
        if w:
            remaining = w.get('remaining_ms')
            known = type(remaining) in (int, float) and remaining >= 0
            decision = w.get('decision') or {}
            task = {key: w[key] for key in ('session', 'task_id', 'revision', 'state')}
            task.update(service=self.env.game, service_label=self.env.label, title=self.title,
                message=w.get('message') or '', reason=w.get('reason') or '',
                remaining_known=known,
                remaining_ms=max(0, int(min(remaining - age * 1000, (self._deadline - time.monotonic()) * 1000))) if known else 0,
                decision_id=decision.get('decision_id') or '', decision_message=decision.get('message') or '',
                can_stop=w['state'] in ACTIVE and w['state'] != 'cancelling',
                can_retry=confirmed and w['state'] == 'needs_decision' and bool(decision.get('decision_id')))
        return {'v': 2, 'type': 'goal.state', 'stream_id': self._stream_id,
                'revision': self._display_revision, 'confirmed': confirmed,
                'confirmed_ago_ms': int(age * 1000), 'valid_for_ms': 10000, 'has_task': bool(w), 'task': task}

    def _publish(self, unknown=False):
        self._display_revision += 1
        state = self.state(unknown)
        if self.publish:
            self.publish(state)

    async def _control(self, m):
        # Check again inside the lock: a queued click must not act on a replacement task.
        async with self._lock:
            w = self.work
            if (not w or m.get('stream_id') != self._stream_id or m.get('session') != w['session']
                    or m.get('task_id') != w['task_id'] or type(m.get('revision')) is not int
                    or m.get('revision') != w['revision']
                    or w['state'] in TERMINAL):
                return
            if m.get('action') == 'stop':
                await self.stop()
            elif (m.get('action') == 'retry' and self.state()['confirmed']
                    and m.get('decision_id') == (w.get('decision') or {}).get('decision_id')):
                await self.answer(m.get('decision_id'), 'retry')

    def on_data(self, packet):
        if getattr(packet, 'topic', None) != TOPIC:
            return
        try:
            m = json.loads(packet.data.decode())
        except (ValueError, AttributeError):
            return
        if isinstance(m, dict) and m.get('v') == 2 and m.get('type') == 'goal.control':
            asyncio.create_task(self._control(m))

    async def close(self):
        if self._watch:
            self._watch.cancel()
            await asyncio.gather(self._watch, return_exceptions=True)
        if self.work and self.work['state'] not in TERMINAL:
            await self.stop()
