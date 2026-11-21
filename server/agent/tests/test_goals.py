"""Common work client tests with a game that has no crafting or recipe vocabulary."""
import asyncio
import copy
import types
import unittest
from unittest.mock import AsyncMock
import goals

class WorkTest(unittest.IsolatedAsyncioTestCase):
    async def test_already_voiced_question_is_not_generated_again(self):
        await self.runner.start('puzzle.solve', {})
        self.runner.say = lambda why, **kw: types.SimpleNamespace(status='queued')
        self.runner.message({'task_id': 'task', 'revision': 1, 'text': 'Which corner?'})
        self.runner.say = lambda why, **kw: self.lines.append(kw)
        self.runner.accept({**self.remote, 'revision': 2, 'state': 'needs_decision',
                            'decision': {'decision_id': 'q', 'message': 'Which corner?'}})
        self.assertEqual(self.lines, [])

    async def test_body_speech_becomes_invalid_when_the_work_changes_or_stops(self):
        await self.runner.start('puzzle.solve', {})
        self.runner.message({'task_id': 'task', 'text': 'Starting.'})
        valid = self.lines[-1]['valid']
        self.assertTrue(valid())
        self.runner.work = {**self.runner.work, 'state': 'cancelling'}
        self.assertFalse(valid())
        self.runner.work = {**self.runner.work, 'state': 'running', 'task_id': 'new'}
        self.assertFalse(valid())

    async def test_a_finished_work_spoken_by_the_body_is_still_recorded_for_the_mind(self):
        recorded = []
        self.runner.record = lambda event_id, fact: recorded.append((event_id, fact))
        await self.runner.start('puzzle.solve', {}, title='木のシャベルを作って')
        self.runner.say = lambda why, **kw: types.SimpleNamespace(status='queued')
        self.runner.message({'task_id': 'task', 'revision': 1, 'text': 'できました。'})
        self.runner.say = lambda why, **kw: self.lines.append(kw)
        self.runner.accept({**self.remote, 'revision': 2, 'state': 'succeeded', 'evidence': {'response': 'できました。'}})
        self.assertEqual(self.lines, [])   # 終わりの言葉は体がもう話す
        self.assertEqual(recorded, [('server:task:succeeded', '頼まれた作業「木のシャベルを作って」が終わった（できた）')])

    async def test_doing_lists_the_works_done_together_without_a_long_gap(self):
        self.assertIsNone(self.runner.doing())
        now = goals.time.time()
        self.runner.recent.extend([{'title': '昔の遊び', 'state': 'succeeded', 'at': now - 3600},
                                   {'title': '木のシャベル', 'state': 'succeeded', 'at': now - 300},
                                   {'title': '土をならす', 'state': 'failed', 'at': now - 60}])
        d = self.runner.doing()
        self.assertEqual([w['request'] for w in d['works']], ['木のシャベル', '土をならす'])
        self.assertEqual(d['works'][1]['result'], 'できなかった')
        self.assertEqual(d['minutes'], 5.0)
        await self.runner.start('puzzle.solve', {}, title='庭を作る')
        self.assertEqual(self.runner.doing()['works'][-1], {'request': '庭を作る', 'result': 'している途中'})

    def setUp(self):
        self.remote = {'version': 1, 'session': 'server', 'task_id': 'task', 'request_id': 'request',
                       'revision': 1, 'state': 'running', 'evidence': {}, 'message': ''}
        self.env = types.SimpleNamespace(game='puzzle', label='Puzzle', linked=True,
            profile={'work': {'version': 1, 'submit': 'submit', 'status': 'status', 'cancel': 'cancel', 'answer': 'answer'}},
            _call=AsyncMock(side_effect=self.call))
        self.lines, self.states = [], []
        self.runner = goals.GoalRunner(lambda why, **kw: self.lines.append(kw), self.states.append, env=self.env)

    async def call(self, name, args, **kw):
        if name == 'cancel':
            self.remote.update(state='cancelled', revision=self.remote['revision'] + 1, message='Stopped')
        return copy.deepcopy(self.remote)

    async def asyncTearDown(self):
        await self.runner.close()

    async def test_requests_an_opaque_capability_without_steps(self):
        r = await self.runner.start('puzzle.solve', {'board': 'abc'}, constraints={'moves': 7}, seconds=20)
        self.assertEqual(r['state'], 'running')
        name, args = self.env._call.await_args_list[0].args
        self.assertEqual(name, 'submit')
        self.assertEqual(args['arguments'], {'board': 'abc'})
        self.assertEqual(args['constraints'], {'moves': 7})
        self.assertEqual(self.runner.state()['v'], 2)
        self.assertNotIn('steps', self.runner.state())
        self.assertEqual((await self.runner.start('other', {}))['status'], 'busy')

    async def test_old_foreign_and_delayed_states_are_rejected(self):
        await self.runner.start('puzzle.solve', {})
        self.assertFalse(self.runner.accept({**self.remote, 'revision': 0}))
        self.assertFalse(self.runner.accept({**self.remote, 'revision': 2, 'session': 'old'}))
        self.assertFalse(self.runner.accept({**self.remote, 'revision': 2, 'task_id': 'other'}))
        self.assertTrue(self.runner.accept({**self.remote, 'revision': 2, 'state': 'succeeded', 'message': 'Verified'}))
        self.assertEqual(len(self.lines), 1)
        self.assertFalse(self.runner.accept({**self.remote, 'revision': 2, 'state': 'succeeded'}))
        self.assertIn('Verified', self.lines[0]['instructions'])

    async def test_cancelling_is_not_stopped_and_decision_needs_matching_id(self):
        await self.runner.start('puzzle.solve', {})
        self.remote.update(state='cancelling', revision=2, reason='stop_unconfirmed')
        self.env._call.side_effect = None
        self.env._call.return_value = copy.deepcopy(self.remote)
        result = await self.runner.stop()
        self.assertEqual(result['state'], 'cancelling')
        self.assertEqual(self.runner.state()['task']['state'], 'cancelling')
        self.assertIsNotNone(self.runner.body_step())
        self.assertEqual((await self.runner.answer('decision', 'retry'))['reason'], 'stale_decision')
        self.remote.update(state='needs_decision', revision=3, decision={'decision_id': 'decision'})
        self.runner.accept(self.remote)
        self.env._call.return_value = copy.deepcopy(self.remote)
        await self.runner.answer('decision', 'retry')
        name, args = self.env._call.await_args.args
        self.assertEqual(name, 'answer')
        self.assertEqual(args, {'task_id': 'task', 'decision_id': 'decision', 'action': 'retry'})

    async def test_a_question_is_answered_with_the_owners_words_and_the_owner_speaks_into_a_running_work(self):
        self.env.profile['work']['say'] = 'say'
        await self.runner.start('puzzle.solve', {})
        self.assertEqual((await self.runner.tell('  '))['reason'], 'invalid_message')
        await self.runner.tell('Use the other corner.')
        self.assertEqual(self.env._call.await_args.args, ('say', {'task_id': 'task', 'message': 'Use the other corner.'}))
        # What the body says during the work is voiced; another work's message is not.
        self.assertTrue(self.runner.message({'task_id': 'task', 'text': 'Starting at the corner.'}))
        self.assertFalse(self.runner.message({'task_id': 'other', 'text': 'x'}))
        self.assertEqual('Starting at the corner.', self.lines[-1]['text'])
        self.remote.update(state='needs_decision', revision=2, reason='owner_question',
                           decision={'decision_id': 'q', 'kind': 'question', 'actions': ['reply', 'cancel'], 'message': 'Which corner?'})
        self.runner.accept(copy.deepcopy(self.remote))
        self.assertFalse(self.runner.state()['task']['can_retry'])
        self.assertEqual((await self.runner.answer('q', 'retry'))['reason'], 'stale_decision')
        self.assertEqual((await self.runner.answer('q', 'reply', ''))['reason'], 'invalid_message')
        self.assertEqual((await self.runner.tell('more'))['reason'], 'not_running')
        await self.runner.answer('q', 'reply', 'The left one.')
        self.assertEqual(self.env._call.await_args.args,
                         ('answer', {'task_id': 'task', 'decision_id': 'q', 'action': 'reply', 'message': 'The left one.'}))

    async def test_a_work_the_game_lengthened_is_not_stopped_at_the_first_deadline(self):
        await self.runner.start('puzzle.solve', {}, seconds=10)
        first = self.runner._deadline
        self.runner.accept({**self.remote, 'revision': 2, 'remaining_ms': 900000})
        self.assertGreater(self.runner._deadline, first + 800)
        self.runner.accept({**self.remote, 'revision': 3, 'remaining_ms': 1000})
        self.assertGreater(self.runner._deadline, first + 800, 'an estimate never shortens the work')

    async def test_a_work_waiting_for_the_owner_is_not_stopped_at_its_deadline(self):
        self.remote.update(state='needs_decision', remaining_ms=60000,
                           decision={'decision_id': 'q', 'kind': 'question', 'actions': ['reply', 'cancel']})
        await self.runner.start('puzzle.solve', {}, seconds=1)
        self.runner._deadline = 0   # the conversation's own deadline has passed while the owner thinks
        await asyncio.sleep(2.1)    # one more round of the watch
        self.assertNotIn('cancel', [c.args[0] for c in self.env._call.await_args_list])
        self.assertGreater(self.runner._deadline, 0)

    async def test_the_plan_graph_of_the_game_is_shown_and_summarised_for_ciel(self):
        await self.runner.start('puzzle.solve', {})
        plan = {'v': 1, 'plan_id': 'p', 'revision': 2, 'title': 'tower', 'finished': False, 'current': ['b'],
                'nodes': [{'id': 'a', 'kind': 'obtain', 'label': 'stone x4', 'state': 'done', 'needs': []},
                          {'id': 'b', 'kind': 'decide', 'label': 'roof', 'state': 'waiting_choice', 'needs': ['a'],
                           'choice': {'question': 'which roof', 'options': [{'id': 'flat'}, {'id': 'peaked'}]}},
                          {'id': 'c', 'kind': 'build', 'label': 'tower', 'state': 'pending', 'needs': ['b']}]}
        self.assertFalse(self.runner.plan({'task_id': 'other', 'plan': plan}))
        self.assertTrue(self.runner.plan({'task_id': 'task', 'plan': plan}))
        self.assertFalse(self.runner.plan({'task_id': 'task', 'plan': {**plan, 'revision': 1}}), 'older revision')
        shown = self.runner.state()['task']['plan']
        self.assertEqual((shown['plan_id'], shown['revision'], len(shown['nodes'])), ('p', 2, 3))
        summary = self.runner.plan_summary()
        self.assertEqual(summary['next'], ['build tower'])
        self.assertEqual(summary['choice'], [{'about': 'roof', 'options': ['flat', 'peaked']}])
        self.assertEqual((summary['done'], summary['steps']), (1, 3))
        context = self.runner.context()
        self.assertNotIn('"nodes"', context)
        self.assertIn('build tower', context)

    async def test_unsupported_version_and_invalid_budget_do_not_submit(self):
        self.env.profile['work']['version'] = 99
        self.assertEqual((await self.runner.start('puzzle.solve', {}))['reason'], 'work_protocol_mismatch')
        self.env._call.assert_not_awaited()
        self.env.profile['work']['version'] = 1
        self.assertEqual((await self.runner.start('puzzle.solve', {}, seconds=True))['reason'], 'invalid_budget')
        self.assertEqual((await self.runner.start('puzzle.solve', {}, seconds=goals.MAX_SECONDS + 1))['reason'], 'invalid_budget')
        self.env._call.assert_not_awaited()

    async def test_transport_error_does_not_report_success(self):
        await self.runner.start('puzzle.solve', {})
        self.env._call.side_effect = None
        self.env._call.return_value = {'status': 'no_answer'}
        await asyncio.sleep(.6)
        self.assertEqual(self.runner.work['state'], 'running')
        self.assertTrue(any(not s['confirmed'] for s in self.states))
        self.assertEqual(self.lines, [])

    async def test_invalid_state_and_all_valid_states(self):
        for change in ({'state': {}}, {'state': 'paused'}, {'version': True}, {'remaining_ms': float('nan')}, {'decision': []}):
            self.assertFalse(self.runner.valid({**self.remote, **change}))
        for revision, state in enumerate(('accepted', 'running', 'needs_decision', 'cancelling', 'cancelled'), 1):
            self.runner.accept({**self.remote, 'revision': revision, 'state': state})
            self.assertEqual(self.runner.state()['task']['state'], state)
            self.assertNotIn('steps', self.runner.state())

    async def test_confirmation_recovers_without_work_revision_change(self):
        await self.runner.start('puzzle.solve', {})
        self.runner._publish(unknown=True)
        self.assertFalse(self.runner.state()['confirmed'])
        self.assertFalse(self.runner.accept(copy.deepcopy(self.remote)))
        self.assertTrue(self.runner.state()['confirmed'])
        self.assertEqual(self.lines, [])

    async def test_remaining_budget_changes_without_state_revision(self):
        self.remote['remaining_ms'] = 20000
        await self.runner.start('puzzle.solve', {}, seconds=20)
        self.remote['remaining_ms'] = 15000
        self.runner.accept(copy.deepcopy(self.remote))
        self.assertTrue(self.runner.state()['confirmed'])
        self.assertLessEqual(self.runner.state()['task']['remaining_ms'], 15000)
        self.remote['remaining_ms'] = 999999
        self.runner.accept(copy.deepcopy(self.remote))
        self.assertLessEqual(self.runner.state()['task']['remaining_ms'], 20000)

    async def test_stale_controls_never_target_new_work(self):
        await self.runner.start('puzzle.solve', {})
        count = self.env._call.await_count
        base = dict(v=2, type='goal.control', stream_id=self.runner._stream_id,
                    session='server', task_id='task', revision=1, action='stop')
        for change in ({'stream_id': 'old'}, {'session': 'old'}, {'task_id': 'old'}, {'revision': 0}):
            await self.runner._control({**base, **change})
        self.assertEqual(self.env._call.await_count, count)
        await self.runner._control(base)
        self.assertEqual(self.runner.work['state'], 'cancelled')

    async def test_control_revalidates_after_waiting_for_lock(self):
        await self.runner.start('puzzle.solve', {})
        await self.runner._lock.acquire()
        pending = asyncio.create_task(self.runner._control(dict(stream_id=self.runner._stream_id,
            session='server', task_id='task', revision=1, action='stop')))
        await asyncio.sleep(0)
        self.runner.accept({**self.remote, 'revision': 2})
        count = self.env._call.await_count
        self.runner._lock.release()
        await pending
        self.assertEqual(self.env._call.await_count, count)

    async def test_old_and_malformed_controls_are_ignored(self):
        import json
        await self.runner.start('puzzle.solve', {})
        count = sum(c.args[0] == 'cancel' for c in self.env._call.await_args_list)
        for message in ([], None, {'v': 1, 'type': 'goal.control', 'action': 'stop'}):
            self.runner.on_data(types.SimpleNamespace(topic='ciel.goal', data=json.dumps(message).encode()))
        await asyncio.sleep(0)
        self.assertEqual(sum(c.args[0] == 'cancel' for c in self.env._call.await_args_list), count)

    async def test_transport_exception_preserves_state_and_watch(self):
        await self.runner.start('puzzle.solve', {})
        self.env._call.side_effect = RuntimeError('offline')
        await asyncio.sleep(.05)
        self.assertFalse(self.runner.state()['confirmed'])
        self.assertEqual(self.runner.state()['task']['state'], 'running')
        self.assertFalse(self.runner._watch.done())

class OneBodyCallTest(unittest.TestCase):
    def test_only_one_moving_tool_per_reply(self):
        # 集めると作るを同時に呼び、体の技が取り合いになって両方失敗した件（2026-11-07）
        import mind
        from livekit.agents import llm
        def chunk(*names):
            calls = [llm.FunctionToolCall(name=n, arguments='{}', call_id=f'c{i}') for i, n in enumerate(names)]
            return llm.ChatChunk(id='x', delta=llm.ChoiceDelta(role='assistant', tool_calls=calls))
        taken = []
        moving = {'collect_blocks', 'craft_item'} | mind.GOAL_ONE   # ゲームの act の道具と、目的の道具（Mind.one_call_tools）
        out, dropped = mind.one_body_call(chunk('collect_blocks', 'look_around', 'craft_item'), taken, moving)
        self.assertEqual([c.name for c in out.delta.tool_calls], ['collect_blocks', 'look_around'])
        self.assertEqual(dropped, ['craft_item'])
        out, dropped = mind.one_body_call(chunk('submit_game_task'), taken, moving)   # 同じ返事の続きの chunk でも
        self.assertIsNone(out)
        self.assertEqual(dropped, ['submit_game_task'])
        out, dropped = mind.one_body_call(chunk('remember_about_speaker'), [], moving)
        self.assertEqual(dropped, [])


if __name__ == '__main__':
    unittest.main()
