"""Game-independent work client. Plans, steps and repairs belong to the MCP server."""
import asyncio
import hashlib
import json
import math
import time
import uuid

import debug_log

TOPIC = 'ciel.goal'
TERMINAL = frozenset(('succeeded', 'failed', 'cancelled'))
# The work contract's ceiling for one work (the game enforces the same limit). The game may
# lengthen a work to its plan's estimate within it; the client follows remaining_ms.
MAX_SECONDS = 1800
# The owner's words handed to a work (the game enforces the same limit).
MAX_MESSAGE = 2000
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
        self._last_body_speech = None
        self._last_body_event = None
        self._stream_id = uuid.uuid4().hex
        self._display_revision = 1
        self._confirmed_at = 0
        self._unknown = False
        self.presence = lambda: 'solo'
        self.owner_name = lambda: None
        self._plan = None   # the game's plan graph (plan v1) for the current work

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

    async def replace(self, capability, arguments, *, constraints=None, seconds=90, title='', valid=lambda: True):
        """Never submit a new objective until the same old work has stopped."""
        old = self.work
        if not old or old['state'] not in ('accepted', 'running', 'needs_decision') or not valid():
            return {'status': 'error', 'reason': 'stale_work'}
        identity = (old['session'], old['task_id'])
        result = await self.stop()
        # A cancellation in flight is not permission to start another work. The caller
        # reports the unconfirmed stop; a new explicit request can retry after status.
        current = self.work
        if (not valid() or not current or (current['session'], current['task_id']) != identity
                or current['state'] not in TERMINAL or self._unknown):
            return {'status': 'error', 'reason': 'stop_unconfirmed'}
        return await self.start(capability, arguments, constraints=constraints, seconds=seconds, title=title)

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
        self._follow_deadline(w)
        debug_log.record('work_state', work=w)
        self._publish()
        if w['state'] in TERMINAL or w['state'] == 'needs_decision':
            key = (w['task_id'], w['state'], (w.get('decision') or {}).get('decision_id'))
            if key not in self._notified:
                self._notified.add(key)
                repeated = ((w.get('decision') or {}).get('message') if w['state'] == 'needs_decision'
                            else (w.get('evidence') or {}).get('response') if w['state'] == 'succeeded' else None)
                if (repeated and self._last_body_speech == (w['session'], w['task_id'], repeated.strip()[:600])
                        and getattr(self._last_body_event, 'status', None) in ('queued', 'generating', 'spoken')):
                    return True
                # Inventory/evidence remain in the current-state supplement, not the event timeline.
                fact = {k: w.get(k) for k in ('task_id', 'state', 'message', 'reason', 'decision')}
                self.say('game', settle=0.2, instructions=json.dumps({'work_result': fact, 'title': self.title}, ensure_ascii=False), merge=True)
        return True

    def _follow_deadline(self, w):
        """A work the game lengthened (its plan's estimate) is not stopped at the first deadline."""
        remaining = w.get('remaining_ms')
        if w['state'] not in TERMINAL and type(remaining) in (int, float):
            self._deadline = max(self._deadline, time.monotonic() + min(remaining / 1000, MAX_SECONDS))

    async def _poll(self, task_id):
        try:
            while self.work and self.work['task_id'] == task_id and self.work['state'] not in TERMINAL:
                if self.work['state'] == 'needs_decision':
                    # The game holds the work's time while it waits for the owner (and limits the wait).
                    self._follow_deadline({**self.work, 'state': 'running'})
                elif time.monotonic() >= self._deadline and self.work['state'] != 'cancelling':
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

    async def answer(self, decision_id, action, message=None):
        """retry or cancel a stopped work, or reply to the body's question with the owner's words."""
        if not self.work:
            return {'status': 'no_task'}
        decision = self.work.get('decision') or {}
        if (self.work['state'] != 'needs_decision' or decision_id != decision.get('decision_id')
                or action not in (decision.get('actions') or ('retry', 'cancel'))):
            return {'status': 'error', 'reason': 'stale_decision'}
        args = {'task_id': self.work['task_id'], 'decision_id': decision_id, 'action': action}
        if action == 'reply':
            if not isinstance(message, str) or not message.strip() or len(message) > MAX_MESSAGE:
                return {'status': 'error', 'reason': 'invalid_message'}
            args['message'] = message.strip()
        r = await self._call('answer', args)
        if not self.accept(r) and r != self.work:
            self._publish(unknown=True)
        return r

    async def tell(self, message):
        """The owner's words to the running work, such as another way to do it."""
        if not self.work or self.work['state'] != 'running':
            return {'status': 'error', 'reason': 'not_running'}
        if not isinstance(message, str) or not message.strip() or len(message) > MAX_MESSAGE:
            return {'status': 'error', 'reason': 'invalid_message'}
        r = await self._call('say', {'task_id': self.work['task_id'], 'message': message.strip()})
        if not self.accept(r) and r != self.work:
            self._publish(unknown=True)
        return r

    def plan(self, e):
        """The game's plan graph for the current work: a newer revision, or a new plan, is shown."""
        w, p = self.work, e.get('plan') if isinstance(e, dict) else None
        if (not w or e.get('task_id') != w['task_id'] or not isinstance(p, dict) or p.get('v') != 1
                or not isinstance(p.get('plan_id'), str) or type(p.get('revision')) is not int or not isinstance(p.get('nodes'), list)):
            return False
        old = self._current_plan()
        if old and old.get('plan_id') == p['plan_id'] and p['revision'] <= old.get('revision', 0):
            return False
        self._plan = {'task_id': w['task_id'], **p}
        self._publish()
        return True

    def _current_plan(self):
        """The newest plan of the current work, from the notices or the work state."""
        w = self.work
        if not w:
            return None
        mine = self._plan if self._plan and self._plan.get('task_id') == w['task_id'] else None
        polled = w.get('plan') if isinstance(w.get('plan'), dict) else None
        if mine and polled and polled.get('plan_id') == mine.get('plan_id'):
            return mine if mine.get('revision', 0) >= polled.get('revision', 0) else polled
        return mine or polled

    def plan_summary(self):
        """A few facts of the plan for Ciel to talk about: what she is doing, what comes next, what waits on a choice."""
        p = self._current_plan()
        if not p:
            return None
        nodes = [n for n in p.get('nodes', []) if isinstance(n, dict)]
        label = lambda n: f"{n.get('kind')} {n.get('label')}"
        waiting = [n for n in nodes if n.get('state') == 'waiting_choice' and n.get('choice')]
        return {'title': p.get('title') or self.title,
                'now': [label(n) for n in nodes if n.get('state') == 'running'][:3],
                'next': [label(n) for n in nodes if n.get('state') in ('ready', 'pending') and not n.get('parent')][:3],
                'choice': [{'about': n.get('label'), 'options': [o.get('id') for o in n['choice'].get('options', [])]} for n in waiting][:1],
                'done': sum(n.get('state') == 'done' for n in nodes), 'steps': len(nodes)}

    def message(self, e):
        """What the body says to the owner while it works (which way it chose, what it is doing)."""
        w = self.work
        text = e.get('text') if isinstance(e, dict) else None
        if not w or e.get('task_id') != w['task_id'] or w['state'] in TERMINAL or not isinstance(text, str) or not text.strip():
            return False
        identity = (w['session'], w['task_id'])
        text = text.strip()[:600]
        event_id = hashlib.sha256(json.dumps([*identity, e.get('revision'), text]).encode()).hexdigest()
        event = self.say('game', settle=0.2, text=text,
                 event_id=event_id,
                 valid=lambda: bool(self.work and self.env.linked and not self._unknown
                                    and (self.work['session'], self.work['task_id']) == identity
                                    and self.work['state'] not in ('cancelling', 'cancelled', 'failed')))
        if event is not None:
            self._last_body_speech = (*identity, text)
            self._last_body_event = event
        return True

    def body_step(self):
        return self.title if self.work and self.work['state'] in ACTIVE else None

    def context(self):
        if not self.work:
            return None
        # The plan graph goes to the app whole; Ciel gets what she would say about it.
        work = {k: v for k, v in self.work.items() if k != 'plan'}
        plan = self.plan_summary()
        return '[今の作業] ' + json.dumps({'title': self.title, 'work': work, **({'plan': plan} if plan else {})}, ensure_ascii=False)

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
                can_retry=(confirmed and w['state'] == 'needs_decision' and bool(decision.get('decision_id'))
                           and 'retry' in (decision.get('actions') or ('retry',))))
            # The game's plan graph, as the game reported it (plan v1); the app only shows it.
            plan = self._current_plan()
            if plan:
                task['plan'] = {k: v for k, v in plan.items() if k != 'task_id'}
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
