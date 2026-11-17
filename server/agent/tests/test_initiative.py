import asyncio
import json
import unittest
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock, Mock, patch

from conversation import Conversation
from initiative import Initiative
from game_decision import GameDecision


class InitiativeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 0.
        self.history = Conversation()
        self.session = Obj(user_state='listening')
        self.handle = asyncio.get_running_loop().create_future()
        self.mouth = Obj(session=self.session, busy=Mock(return_value=False),
                         say=Mock(return_value=self.handle))
        self.decider = Obj(consider=AsyncMock(return_value={'status': 'silent', 'say': '', 'acted': False}))
        self.loop = Initiative(self.history, self.mouth, self.decider, 'decide', 'quiet', clock=lambda: self.now)

    async def asyncTearDown(self):
        self.loop._handle = None  # the fixture uses a Future instead of a LiveKit SpeechHandle
        await self.loop.close()

    def add(self, role='user', text='hello', label='不明'):
        t = self.history.reserve(role=role)
        self.history.complete(t, text, label=label)
        return t

    async def schedule(self):
        self.loop.step()
        self.now += 9
        self.loop.step()
        await asyncio.sleep(0)

    async def test_observer_distinguishes_waiting_and_failed_decision(self):
        states = []
        self.loop.observe = lambda **state: states.append(state)
        self.loop.step()
        self.assertEqual(states[-1]['reason'], 'new_event')
        self.add()
        self.loop.step()
        self.assertEqual(states[-1]['reason'], 'quiet')
        self.now += 9
        self.loop.step()
        await asyncio.sleep(0)
        self.assertEqual(states[-1]['phase'], 'scheduled')
        self.decider.consider.return_value = dict(status='failed', acted=False, say='')
        await self.loop.reply([], [])
        self.assertTrue(any(s['phase'] == 'deciding' for s in states))
        self.assertEqual(states[-1]['outcome'], 'error')
        self.assertNotEqual(states[-1]['outcome'], 'silent')
        self.handle.set_result(None)

    async def test_idle_alone_and_own_speech_never_rearm(self):
        await self.schedule()
        self.mouth.say.assert_not_called()
        self.add()
        await self.schedule()
        self.mouth.say.assert_called_once()
        self.assertEqual(await self.loop.reply([], []), '')
        self.assertEqual(self.loop.counts['silent'], 1)
        self.assertEqual(await self.loop.reply([], []), '')
        self.decider.consider.assert_awaited_once()
        self.handle.set_result(None)
        await asyncio.sleep(0)
        self.add('assistant', 'a thought')
        self.now += 1000
        await self.schedule()
        self.mouth.say.assert_called_once()

    async def test_comments_and_public_mode_do_not_trigger(self):
        self.add(label='コメント・viewer')
        await self.schedule()
        self.mouth.say.assert_not_called()
        self.add()
        self.loop.allowed = lambda: False
        await self.schedule()
        self.mouth.say.assert_not_called()

    async def test_opening_greeting_can_trigger_once(self):
        self.add('assistant', 'こんにちは')
        await self.schedule()
        self.mouth.say.assert_called_once()
        self.handle.set_result(None)
        await asyncio.sleep(0)
        self.add('assistant', 'self started words')
        self.now += 100
        await self.schedule()
        self.mouth.say.assert_called_once()

    async def test_new_input_invalidates_inflight_result(self):
        self.add()
        await self.schedule()
        async def late(*args, **kwargs):
            self.add(text='new words')
            self.assertFalse(kwargs['valid']())
            return {'status': 'spoken', 'say': 'stale', 'acted': False}
        self.decider.consider.side_effect = late
        self.assertEqual(await self.loop.reply([], []), '')

    async def test_speech_interrupts_inference_and_playout(self):
        self.add()
        await self.schedule()
        started = asyncio.Event()
        async def wait(*args, **kwargs):
            started.set()
            await asyncio.Future()
        self.decider.consider.side_effect = wait
        self.loop._handle = Obj(interrupt=Mock())
        task = asyncio.create_task(self.loop.reply([], []))
        await started.wait()
        self.session.user_state = 'speaking'
        self.loop.on_user_state(Obj(new_state='speaking'))
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.loop._handle.interrupt.assert_called_once_with(force=True)

    async def test_busy_restarts_quiet_interval(self):
        self.add()
        self.loop.step()
        self.now = 20
        self.mouth.busy.return_value = True
        self.loop.step()
        self.mouth.busy.return_value = False
        self.now = 25
        self.loop.step()
        self.mouth.say.assert_not_called()
        self.now = 29
        self.loop.step()
        await asyncio.sleep(0)
        self.mouth.say.assert_called_once()


class AutonomousDecisionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.create = AsyncMock()
        self.client = Obj(chat=Obj(completions=Obj(create=self.create)), close=AsyncMock())
        self.env = Obj(playing=lambda: True, _connection_epoch=1, tools=[], meta={},
            profile={'work': {'version': 1, 'capabilities': [{'name': 'game.goal',
                'handoff': {'version': 1, 'argument': 'request', 'constraints': {}, 'seconds': 120}}]}})
        self.runner = Obj(env=self.env, work=None, body_step=lambda: None,
                          start=AsyncMock(return_value={'status': 'accepted'}))
        self.decision = GameDecision(self.runner, 'regular', client=self.client)

    def response(self, act, say=None):
        return Obj(usage=None, choices=[Obj(message=Obj(content=json.dumps({'say': say or [], 'act': act})))])

    async def consider(self, **kwargs):
        return await self.decision.consider([{'role': 'system', 'content': 'same prefix'}], [],
                                           'initiative {actions}', **kwargs)

    async def test_silence_uses_same_prefix_and_does_not_need_a_game(self):
        self.decision.runner = None
        self.create.return_value = self.response({'kind': 'none'})
        out = await self.consider()
        self.assertEqual(out['status'], 'silent')
        sent = self.create.await_args.kwargs
        self.assertEqual(sent['messages'][0], {'role': 'system', 'content': 'same prefix'})
        self.assertEqual(sent['response_format']['json_schema']['schema']['properties']['say']['minItems'], 0)

    async def test_new_self_chosen_work_uses_existing_runner(self):
        self.create.return_value = self.response({'kind': 'work', 'request': 'collect wood'})
        out = await self.consider()
        self.assertEqual(out['status'], 'acted')
        self.runner.start.assert_awaited_once()
        self.assertEqual(self.runner.start.await_args.args, ('game.goal', {'request': 'collect wood'}))

    async def test_work_state_change_during_inference_blocks_action(self):
        async def change(**kwargs):
            self.runner.work = {'state': 'running'}
            return self.response({'kind': 'work', 'request': 'new goal'})
        self.create.side_effect = change
        self.assertEqual((await self.consider())['status'], 'cancelled')
        self.runner.start.assert_not_awaited()

    async def test_active_failed_cancelled_and_confirmation_only_allow_speech(self):
        for state in ('running', 'accepted', 'needs_decision', 'cancelling', 'cancelled', 'failed', 'unknown'):
            with self.subTest(state=state):
                self.runner.work = {'state': state}
                self.create.return_value = self.response({'kind': 'work', 'request': 'new goal'})
                self.assertEqual((await self.consider())['status'], 'failed')
        self.runner.start.assert_not_awaited()

    async def test_stop_or_authority_loss_blocks_autonomous_work(self):
        self.create.return_value = self.response({'kind': 'work', 'request': 'new goal'})
        self.decision.autonomy_allowed = False
        self.assertEqual((await self.consider())['status'], 'failed')
        self.decision.autonomy_allowed = True
        self.decision.authorized = lambda: False
        self.assertEqual((await self.consider())['status'], 'failed')
        self.runner.start.assert_not_awaited()

    async def test_cancelled_input_never_speaks_or_acts(self):
        self.assertEqual((await self.consider(valid=lambda: False))['status'], 'cancelled')
        self.create.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
