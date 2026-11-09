import asyncio
import contextlib
import json
from types import SimpleNamespace as Obj
import unittest
from unittest.mock import AsyncMock, patch

import mouth
import game_env
from touch import TouchReactions


class Handle:
    def __init__(self, name, complete=True):
        self.id, self.interrupted = name, False
        self.done = asyncio.get_running_loop().create_future()
        if complete:
            self.done.set_result(None)

    def __await__(self):
        return asyncio.shield(self.done).__await__()

    def interrupt(self, *, force=False):
        self.interrupted = True
        if not self.done.done():
            self.done.set_result(None)


class Session:
    def __init__(self):
        self.agent_state = self.user_state = 'listening'
        self.userdata = Obj()
        self.current_speech = None
        self.calls = []
        self.complete = True

    def generate_reply(self, **kwargs):
        self.calls.append(kwargs)
        self.current_speech = Handle(str(len(self.calls)), self.complete)
        if self.complete:
            asyncio.get_running_loop().call_soon(lambda: self.userdata.mouth.reactions.on_said(
                Obj(item=Obj(role='assistant', interrupted=False, text_content='reaction'))))
        return self.current_speech


class ReactionsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session = Session()
        self.mouth = self.session.userdata.mouth = mouth.Mouth(self.session)
        self.hub = self.mouth.reactions
        self.outputs = []
        self.hub.publish = self.outputs.append
        self.now = 100.
        self.hub.clock = self.hub.wall = lambda: self.now

    async def asyncTearDown(self):
        await self.hub.close()

    async def until(self, predicate):
        for _ in range(100):
            if predicate():
                return
            await asyncio.sleep(.01)
        self.fail('reaction did not progress')

    def emit(self, source='game', kind='game.damage', **kw):
        return self.hub.submit(source, kind, {'fact': 'observed'}, why='game',
                               kwargs={'instructions': kind}, **kw)

    async def test_unloaded_service_reacts_and_expression_does_not_wait_for_llm(self):
        event = self.emit(expression='teary')
        self.assertEqual(self.outputs[0]['expression'], 'teary')
        await self.until(lambda: event.status == 'spoken')
        self.assertEqual(self.session.calls, [{'instructions': 'game.damage'}])

    async def test_damage_precedes_work_and_comment(self):
        self.session.user_state = 'speaking'
        work = self.emit('work', 'work.result')
        self.emit('comment', 'comment.received')
        pain = self.emit()
        self.session.user_state = 'listening'
        await self.until(lambda: work.status == 'spoken')
        self.assertEqual(self.session.calls[0]['instructions'], 'game.damage')
        self.assertEqual(pain.status, 'spoken')

    async def test_deduplication_epoch_and_sequence_validation(self):
        self.session.user_state = 'speaking'
        envelope = self.hub.envelope('game', 'game.damage', {}, event_id='same')
        first = self.hub.receive('game', envelope, why='game')
        self.assertIsNotNone(first)
        self.assertIsNone(self.hub.receive('game', envelope, why='game'))
        self.hub.reset('game')
        self.assertEqual(first.status, 'disconnected')
        self.assertIsNone(self.hub.receive('game', envelope, why='game'))

    async def test_rejects_unsupported_malformed_oversized_and_old_events(self):
        valid = self.hub.envelope('game', 'game.damage', {})
        for fields in ({'v': True}, {'v': 2}, {'seq': '1'}, {'kind': 'comment.received'},
                       {'occurred_at': 200}, {'occurred_at': 50}, {'ttl_ms': float('nan')},
                       {'payload': {'text': 'x' * 9000}}, {'payload': None}):
            self.assertIsNone(self.hub.receive('game', {**valid, **fields}, why='game'))
        self.assertFalse(self.hub.queue)

    async def test_expiry_drops_speech_but_keeps_immediate_expression(self):
        self.session.user_state = 'speaking'
        event = self.emit(expression='teary')
        self.now += 6
        await self.until(lambda: event.status == 'expired')
        self.assertEqual(len(self.outputs), 1)
        self.assertFalse(self.session.calls)

    async def test_expression_lease_blocks_song_and_model_but_expires(self):
        self.session.user_state = 'speaking'
        self.emit(expression='teary')
        self.hub.submit('song', 'song.change', {}, why='song', expression='excited')
        self.assertFalse(self.hub.expression('happy'))
        self.assertEqual([o['expression'] for o in self.outputs], ['teary'])
        self.now += 4
        self.assertTrue(self.hub.expression('happy'))

    async def test_song_changes_face_without_speech_and_comments_expire(self):
        self.hub.singing = lambda: True
        event = self.hub.submit('song', 'song.change', {}, why='song', expression='relaxed')
        self.assertEqual(event.status, 'visual_only')
        comment = self.emit('comment', 'comment.received')
        self.now += 31
        await self.until(lambda: comment.status == 'expired')
        self.assertFalse(self.session.calls)

    async def test_queue_is_bounded_and_reserves_space_for_damage(self):
        self.session.user_state = 'speaking'
        self.hub.LIMIT = 1
        low = self.emit('comment', 'comment.received')
        pain = self.emit()
        self.assertEqual(low.status, 'overflow')
        rejected = self.emit('work', 'work.result')
        self.assertEqual(rejected.status, 'overflow')
        self.assertEqual(list(self.hub.queue.values()), [pain])

    async def test_preemption_stops_generated_low_priority_audio(self):
        self.session.complete = False
        low = self.emit('comment', 'comment.received')
        await self.until(lambda: low.handle is not None)
        old_id = low.handle.id
        self.emit()
        await self.until(lambda: len(self.session.calls) == 2)
        self.assertTrue(low.handle.interrupted)
        self.assertEqual(low.status, 'preempted')
        self.assertFalse(self.hub.allowed(old_id))

    async def test_expiry_interrupts_generation_without_marking_spoken(self):
        self.session.complete = False
        envelope = self.hub.envelope('game', 'game.damage', {})
        envelope['ttl_ms'] = 60
        event = self.hub.receive('game', envelope, why='game')
        await self.until(lambda: event.status == 'expired')
        self.assertTrue(event.handle.interrupted)
        self.assertFalse(self.hub.allowed(event.handle.id))

    async def test_touch_context_does_not_duplicate_speech_and_cancel_is_not_spoken(self):
        self.session.user_state = 'speaking'
        self.session.current_speech = Handle('owner')
        touch = TouchReactions(self.session)
        touch.on_data(Obj(topic='ciel.touch', data=json.dumps({'v': 2, 'type': 'user.touch', 'event_id': 'pull1', 'source_epoch': 'app1',
            'seq': 1, 'occurred_at': self.now, 'part': 'cheek', 'gesture': 'pull',
            'phase': 'start', 'strength': 'hard', 'expression': 'teary'}).encode()))
        self.assertFalse(self.outputs)
        event = next(iter(self.hub.queue.values()))
        self.assertIn('引っ張', touch.take())
        self.assertEqual(event.status, 'attached')
        self.hub.on_said(Obj(item=Obj(role='assistant', interrupted=True, text_content='unfinished')))
        self.assertEqual(event.status, 'cancelled')
        self.session.user_state = 'listening'
        await asyncio.sleep(.06)
        self.assertFalse(self.session.calls)

    async def test_comment_keeps_authority_and_stable_identifier(self):
        reasons = []
        self.mouth.before_say = reasons.append
        self.assertIsNotNone(await self.mouth.react_comment('comment', instructions='data', event_id='c1'))
        self.assertEqual(reasons, ['comment'])
        self.assertIsNone(await self.mouth.react_comment('comment', instructions='data', event_id='c1'))

    async def test_cancelling_comment_wait_removes_pending_reply(self):
        self.session.user_state = 'speaking'
        task = asyncio.create_task(self.mouth.react_comment('comment', instructions='data'))
        await asyncio.sleep(0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(self.hub.queue)

    async def test_old_touch_contract_and_replayed_native_touch_are_rejected(self):
        self.session.user_state = 'speaking'
        touch = TouchReactions(self.session)
        data = {'v': 2, 'type': 'user.touch', 'event_id': 'touch1', 'source_epoch': 'app1',
                'seq': 1, 'occurred_at': self.now, 'part': 'cheek', 'gesture': 'pull',
                'phase': 'start', 'strength': 'hard', 'expression': 'teary'}
        def send(value):
            touch.on_data(Obj(topic='ciel.touch', data=json.dumps(value).encode()))
        send({**data, 'v': 1})
        send({**data, 'part': []})
        self.assertFalse(self.hub.queue)
        send(data)
        send(data)
        self.assertEqual(len(self.hub.queue), 1)
        touch.reset()
        send({**data, 'event_id': 'touch2', 'source_epoch': 'new', 'occurred_at': self.now - 10})
        self.assertFalse(self.hub.queue)

    async def test_completed_handle_without_output_is_not_marked_spoken(self):
        self.session.complete = False
        event = self.emit()
        await self.until(lambda: event.handle is not None)
        event.handle.done.set_result(None)
        await self.until(lambda: event.status != 'generating')
        self.assertEqual(event.status, 'unconfirmed')

    async def test_interrupted_handle_blocks_late_tool_continuation_before_ack(self):
        self.session.complete = False
        event = self.emit('comment', 'comment.received')
        await self.until(lambda: event.handle is not None)
        event.handle.interrupt(force=True)
        self.assertFalse(self.hub.allowed(event.handle.id))
        await self.until(lambda: event.status == 'cancelled')

    async def test_settle_requires_a_continuous_pause(self):
        self.session.user_state = 'speaking'
        event = self.emit('game', 'game.notice', settle=2)
        await asyncio.sleep(.06)
        self.session.user_state = 'listening'
        await asyncio.sleep(.06)
        self.now += 1.5
        self.session.user_state = 'speaking'
        await asyncio.sleep(.06)
        self.session.user_state = 'listening'
        await asyncio.sleep(.06)
        self.now += 1
        await asyncio.sleep(.06)
        self.assertFalse(self.session.calls)
        self.now += 1.1
        await self.until(lambda: event.status == 'spoken')

    async def test_only_fatal_owned_game_event_requests_emergency_song_stop(self):
        self.session.user_state = 'speaking'
        stopped = []
        self.hub.emergency = lambda: stopped.append(True)
        self.mouth.react_latest('game', instructions='damage', reaction_kind='hurt')
        self.assertFalse(stopped)
        self.mouth.react_latest('game', instructions='fatal', reaction_kind='died')
        self.assertEqual(stopped, [True])

    async def test_game_callbacks_ignore_initialization_old_and_closed_connections(self):
        env = game_env.GameEnv('test', 'http://unused')
        env._on_log = AsyncMock()
        @contextlib.asynccontextmanager
        async def stream(*args, **kwargs):
            yield None, None, None
        sessions = []
        class Client:
            def __init__(self, *args, logging_callback, **kwargs):
                self.callback = logging_callback
                sessions.append(self)
            async def __aenter__(self):
                await self.callback('during initialization')
                return self
            async def __aexit__(self, *args):
                pass
        with patch('game_env.streamablehttp_client', stream), patch('game_env.ClientSession', Client):
            async with env._connect_http() as connection:
                env._session = connection
                await connection.callback('current')
                env._session = object()
                await connection.callback('old')
            await connection.callback('closed')
        env._on_log.assert_awaited_once_with('current')

    async def test_close_interrupts_and_blocks_late_input(self):
        self.session.complete = False
        event = self.emit()
        await self.until(lambda: event.handle is not None)
        await self.hub.close()
        self.assertTrue(event.handle.interrupted)
        self.assertFalse(self.hub.allowed(event.handle.id))
        self.assertIsNone(self.emit())
