"""Two entry points into the actual companion; neither decides benchmark success."""
import asyncio
import json
import os
import uuid
from pathlib import Path


class BodyDriver:
    def __init__(self, url, trace, **_):
        self.url, self.trace = url, trace
        self.env = self.runner = self.task = None
        self.goal_state = {}

    async def open(self):
        import game_env
        import goals
        self.env = game_env.GameEnv('minecraft', self.url)
        original = self.env._call

        async def call(name, args, **kwargs):
            request = uuid.uuid4().hex
            self.trace('game_call', id=request, name=name, arguments=args)
            result = await original(name, args, **kwargs)
            self.trace('game_result', id=request, name=name, result={k:v for k,v in result.items() if k != '_images'})
            return result

        self.env._call = call
        original_done = self.env._task_done

        def task_done(event):
            original_done(event)
            key = self.env._task_key(event)
            if self.env._completed.get(key) is event:
                self.trace('game_task_result',id=key,ok=bool(event.get('ok')),failed=bool(event.get('failed')),
                           reason=event.get('reason'),title=event.get('title'),snapshot=bool(event.get('_snapshot')))

        self.env._task_done = task_done
        original_event = self.env.on_event
        def event(e):
            original_event(e)
            if e.get('kind') in ('work_action', 'work_action_result'):
                self.trace(e['kind'], **{k: v for k, v in e.items() if k != 'kind'})
        self.env.on_event = event
        if not await self.env.prepare():
            raise RuntimeError('Benchmark MCP is unavailable')
        self.env.wanted = True
        await self.env._link(True)
        if not self.env.playing():
            raise RuntimeError('Benchmark body is busy or not spawned')

        def publish(state):
            self.goal_state = state
            self.trace('goal_state', state=state)

        self.runner = goals.GoalRunner(lambda why, **kw: self.trace('notice', why=why, **kw), publish=publish, env=self.env)
        self.env.goals = self.runner

    async def submit(self, task):
        if task.get('navigation'):
            self.task = asyncio.create_task(self.env._call(task['body_call']['name'], task['body_call']['arguments']))
            return
        self.task = asyncio.create_task(self.runner.start('minecraft.obtain_item',
            {'item': task['item'], 'quantity': task['count'], 'quantity_mode': 'gain' if task.get('action') else 'inventory_target'},
            constraints={'resource_scope': 'search', 'failure_policy': 'ask'}, title=task['prompt'], seconds=task.get('budget', {}).get('seconds', 90)))

    async def stop(self, task):
        if task.get('navigation'):
            await self.env._call('minecraft_stop_moving', {})
            return
        await self.runner.stop()

    def events(self):
        if self.task and self.task.done() and not self.task.cancelled():
            self.task.result()
        return []

    def stopped(self):
        return (self.goal_state.get('task') or {}).get('state') == 'cancelled'

    def failure_reason(self):
        if self.runner and (self.runner.work or {}).get('state') == 'needs_decision':
            return 'needs_mind'
        if (self.goal_state.get('task') or {}).get('state') in ('needs_decision','failed'):
            return 'body_cannot_continue'
        return None

    def report_complete(self, after):
        return (self.goal_state.get('task') or {}).get('state') == 'succeeded'

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        if self.runner:
            await self.runner.close()
        if self.env:
            await self.env.close()


class ConversationDriver:
    def __init__(self, agent, backend, model_id, debug_dir, trace, **_):
        self.agent, self.backend, self.debug_dir, self.trace = agent, backend, Path(debug_dir), trace
        self.model_id = model_id
        self.name = 'minecraft-bench-' + uuid.uuid4().hex
        self.trial = self.name.rsplit('-',1)[-1]
        self.room = self.lk = None
        self.created = False
        self.path, self.offset = None, 0
        self.goal_state = {}
        self.tasks = set()
        self.last_reply_at = 0
        self._goal_protocol_error = False

    def _receive_goal_state(self, state):
        task = state.get('task') if isinstance(state, dict) else None
        if (not isinstance(state, dict) or state.get('v') != 2 or state.get('type') != 'goal.state'
                or type(state.get('has_task')) is not bool or type(state.get('confirmed')) is not bool
                or not state.get('stream_id') or type(state.get('revision')) is not int or state['revision'] <= 0
                or state.get('valid_for_ms') != 10000
                or (state.get('has_task') and (not isinstance(task, dict) or not task.get('task_id') or not task.get('session')
                    or type(task.get('revision')) is not int or task['revision'] <= 0 or task.get('state') not in
                    ('accepted', 'running', 'needs_decision', 'cancelling', 'succeeded', 'failed', 'cancelled')))):
            self._goal_protocol_error = True
            self.trace('work_display_protocol_error')
            return
        self.goal_state = state
        self.trace('goal_state', state=state)

    async def open(self):
        from livekit import api, rtc
        import benchmark_contract
        self.room, self.lk = rtc.Room(), api.LiveKitAPI()
        ready, linked = asyncio.Event(), asyncio.Event()

        @self.room.on('data_received')
        def data(packet):
            try:
                state = json.loads(packet.data.decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                return
            if not isinstance(state, dict):
                return
            if packet.topic == 'ciel.event' and state.get('type') == 'env.list':
                ready.set()
            if packet.topic == 'ciel.event' and state.get('type') == 'env.state' and state.get('game') == 'minecraft':
                if state.get('playing'):
                    linked.set()
            if packet.topic == 'ciel.goal':
                self._receive_goal_state(state)

        async def read(reader):
            self.trace('transcription', text=await reader.read_all())

        def transcription(reader, identity):
            task = asyncio.create_task(read(reader))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)

        self.room.register_text_stream_handler('lk.transcription', transcription)
        await self.lk.room.create_room(api.CreateRoomRequest(
            name=self.name, agents=[api.RoomAgentDispatch(agent_name=self.agent,
                metadata=benchmark_contract.metadata(self.backend,self.model_id,self.trial))]))
        self.created = True
        token = (api.AccessToken().with_identity('benchmark-user').with_name('ベンチマーク')
                 .with_grants(api.VideoGrants(room_join=True, room=self.name)).to_jwt())
        await self.room.connect(os.environ['LIVEKIT_URL'], token)
        await asyncio.wait_for(ready.wait(), 90)
        paths = list(self.debug_dir.glob('*-' + self.name + '.jsonl'))
        if len(paths) != 1:
            raise RuntimeError('Benchmark debug log is missing; runner must share agent debug directory')
        self.path = paths[0]
        records = self.events()
        async with asyncio.timeout(10):
            while not any(e.get('kind') == 'benchmark_ready' for e in records):
                await asyncio.sleep(0.05)
                records.extend(self.events())
        start = next((e for e in records if e.get('kind') == 'start'), {})
        if (not start.get('benchmark') or start.get('backend') != self.backend or start.get('input') != 'text'
                or start.get('benchmark_model_id') != self.model_id or start.get('benchmark_trial') != self.trial):
            raise RuntimeError('Agent did not attest benchmark isolation / requested backend / text input')
        if not any(e.get('kind') == 'settings' and e.get('persona_sha256') for e in records):
            raise RuntimeError('Missing persona fingerprint')
        for record in records:
            self.trace('agent_event', event=record)
        await self.room.local_participant.publish_data(
            json.dumps({'v':1, 'type':'env.link', 'game':'minecraft', 'on':True}), reliable=True, topic='ciel.game')
        await asyncio.wait_for(linked.wait(), 30)

    async def submit(self, task):
        await self.room.local_participant.send_text(task['prompt'], topic='lk.chat')

    async def stop(self, task):
        await self.room.local_participant.send_text(task['stop_prompt'], topic='lk.chat')

    def events(self):
        if self._goal_protocol_error:
            raise RuntimeError('Work display protocol mismatch; update the benchmark and agent together')
        if not self.path:
            return []
        events = []
        with self.path.open(encoding='utf-8') as f:
            f.seek(self.offset)
            while True:
                offset = f.tell()
                line = f.readline()
                if not line or not line.endswith('\n'):
                    self.offset = offset
                    break
                event = json.loads(line)
                events.append(event)
                if event.get('kind') == 'item' and event.get('role') == 'assistant' and not event.get('interrupted'):
                    self.last_reply_at = event['t']
                self.offset = f.tell()
        return events

    def stopped(self):
        return (self.goal_state.get('task') or {}).get('state') == 'cancelled'

    def report_complete(self, after):
        return self.last_reply_at >= after

    async def close(self):
        try:
            if self.room:
                await self.room.disconnect()
            if self.tasks:
                await asyncio.gather(*self.tasks, return_exceptions=True)
        finally:
            if self.lk:
                try:
                    if self.created:
                        from livekit import api
                        await self.lk.room.delete_room(api.DeleteRoomRequest(room=self.name))
                finally:
                    await self.lk.aclose()


async def wait_body_released(url, timeout=90):
    """A deleted LiveKit room may still be releasing its MCP session."""
    import game_env
    env = game_env.GameEnv('minecraft',url)
    try:
        if not await env.prepare():
            raise RuntimeError('Cannot verify benchmark body release')
        async with asyncio.timeout(timeout):
            while True:
                env.wanted = True
                # busy is deliberately sticky in the normal app; explicitly retry here.
                env.reason = 'off'
                await env._link(True)
                body = env._body
                if env.playing() and env._body_protocol_valid and not any(body.get(k) for k in ('current','pending','owner','blocked')):
                    return
                await asyncio.sleep(0.5)
    finally:
        await env.close()
