"""Game-independent work client. Plans, steps and repairs belong to the MCP server."""
import asyncio
import json
import time
import uuid

import debug_log

TOPIC = 'ciel.goal'
TERMINAL = frozenset(('succeeded', 'failed', 'cancelled'))
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
        self.notice = None
        self.spoken_notice = None
        self._display_id = 0
        self.presence = lambda: 'solo'
        self.owner_name = lambda: None

    def _tool(self, key):
        return (self.env.profile.get('work') or {}).get(key)

    async def _call(self, key, args):
        if not self.env.linked or not self._tool(key):
            return {'status': 'unavailable'}
        return await self.env._call(self._tool(key), args, timeout=6)

    async def start(self, capability, arguments, *, constraints=None, seconds=90, title='', request_id=None):
        async with self._lock:
            if self.work and self.work['state'] not in TERMINAL:
                return {'status': 'busy'}
            if not self.env or (self.env.profile.get('work') or {}).get('version') != 1:
                return {'status': 'error', 'reason': 'work_protocol_mismatch'}
            if type(seconds) not in (int, float) or not 0 < seconds <= 120:
                return {'status': 'error', 'reason': 'invalid_budget'}
            self._deadline = time.monotonic() + seconds
            self.title = title or capability
            r = await self._call('submit', {'request_id': request_id or uuid.uuid4().hex, 'capability': capability,
                'arguments': arguments, 'constraints': constraints or {}, 'budget_ms': int(seconds * 1000)})
            if not self.valid(r):
                return r if r.get('status') else {'status': 'error', 'reason': 'work_protocol_mismatch'}
            self.work = None
            self._display_id += 1
            self.accept(r)
            if self._watch:
                self._watch.cancel()
            self._watch = asyncio.create_task(self._poll(r['task_id']))
            return r

    @staticmethod
    def valid(w):
        return (isinstance(w, dict) and w.get('version') == 1 and w.get('state') in STATES
                and isinstance(w.get('task_id'), str) and bool(w['task_id']) and isinstance(w.get('session'), str)
                and type(w.get('revision')) is int and w['revision'] > 0)

    def accept(self, w):
        if not self.valid(w):
            return False
        if self.work and (w['task_id'] != self.work['task_id'] or w['session'] != self.work['session']
                          or w['revision'] <= self.work['revision']):
            return False
        if self.work and self.work['state'] in TERMINAL and w['state'] != self.work['state']:
            return False
        self.work = w
        debug_log.record('work_state', work=w)
        self._publish()
        if w['state'] in TERMINAL or w['state'] == 'needs_decision':
            key = (w['task_id'], w['state'], (w.get('decision') or {}).get('decision_id'))
            if key not in self._notified:
                self._notified.add(key)
                self.notice = (key, w.get('message') or w.get('reason') or w['state'])
                self.say('game', settle=0.2, instructions=json.dumps({'work_result': w, 'title': self.title}, ensure_ascii=False), merge=True)
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
                else:
                    self.accept(r)
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            pass

    async def stop(self, **_):
        if not self.work:
            return {'status': 'no_task'}
        r = await self._call('cancel', {'task_id': self.work['task_id']})
        self.accept(r)
        return r

    async def answer(self, decision_id, action):
        if not self.work:
            return {'status': 'no_task'}
        r = await self._call('answer', {'task_id': self.work['task_id'], 'decision_id': decision_id, 'action': action})
        self.accept(r)
        return r

    def body_step(self):
        return self.title if self.work and self.work['state'] in ACTIVE else None

    def context(self):
        return '[今の作業] ' + json.dumps({'title': self.title, 'work': self.work}, ensure_ascii=False) if self.work else None

    def status(self):
        return self.work or {'status': 'no_task'}

    def report(self):
        self.spoken_notice = self.notice
        return self.notice[1] if self.notice else None

    def reported(self):
        if self.spoken_notice == self.notice:
            self.notice = None
        self.spoken_notice = None

    def state(self, unknown=False):
        # Existing UI projection; no recipe steps or separate execution state lives here.
        w = self.work
        status = {'accepted': 'planning', 'running': 'running', 'needs_decision': 'paused', 'cancelling': 'paused',
                  'succeeded': 'done', 'failed': 'failed', 'cancelled': 'stopped'}
        return {'v': 1, 'type': 'goal.state', 'goal': ({'id': self._display_id, 'game': self.env.game, 'game_label': self.env.label,
            'title': self.title, 'by': 'owner', 'by_label': '持ち主のお願い', 'status': 'paused' if unknown else status[w['state']],
            'why': '', 'task_id': w['task_id'], 'can_resume': w['state'] == 'needs_decision'} if w else None), 'steps': [], 'path': [], 'changes': [], 'next': [],
            'attention': '状態不明・停止未確認' if unknown else (w.get('reason') if w else None)}

    def _publish(self, unknown=False):
        if self.publish:
            self.publish(self.state(unknown))

    def on_data(self, packet):
        if getattr(packet, 'topic', None) != TOPIC:
            return
        try:
            m = json.loads(packet.data.decode())
        except (ValueError, AttributeError):
            return
        if m.get('type') == 'goal.control' and m.get('action') == 'stop':
            asyncio.create_task(self.stop())
        if m.get('type') == 'goal.control' and m.get('action') == 'resume' and self.work and self.work['state'] == 'needs_decision':
            asyncio.create_task(self.answer(self.work['decision']['decision_id'], 'retry'))

    async def close(self):
        if self._watch:
            self._watch.cancel()
            await asyncio.gather(self._watch, return_exceptions=True)
        if self.work and self.work['state'] not in TERMINAL:
            await self.stop()
