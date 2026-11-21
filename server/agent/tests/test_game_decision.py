import asyncio
import json
import jsonschema
import types
import unittest
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock, Mock, patch

from livekit.agents import llm

from conversation import Conversation

import game_decision
from game_decision import GameDecision

HANDOFF = {'version': 1, 'argument': 'request', 'constraints': {}, 'seconds': 120}


class DecisionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        come = types.SimpleNamespace(id='game_come', info=types.SimpleNamespace(raw_schema={
            'name': 'game_come', 'description': 'come', 'parameters': {'type': 'object', 'properties': {}}}))
        self.env = types.SimpleNamespace(playing=lambda: True, _connection_epoch=1, tools=[come],
            meta={'game_come': {'ciel/role': 'act'}}, use=AsyncMock(return_value={'status': 'started'}),
            profile={'work': {'version': 1, 'capabilities': [{'name': 'game.goal', 'description': 'work',
                     'arguments': {'type': 'object'}, 'constraints': {}, 'handoff': HANDOFF}]}})
        self.runner = types.SimpleNamespace(env=self.env, work=None, status=lambda: {}, body_step=lambda: None,
            start=AsyncMock(return_value={'task_id': 't', 'status': 'accepted'}),
            stop=AsyncMock(return_value={'state': 'cancelled'}), tell=AsyncMock(return_value={'state': 'running'}),
            answer=AsyncMock(return_value={'state': 'running'}))
        self.create = AsyncMock()
        client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create)),
                                       close=AsyncMock())
        self.decision = GameDecision(self.runner, 'decide\n{actions}', client=client)

    @staticmethod
    def reply(value):
        if not game_decision.models.is_local('mind') and 'arguments' in value.get('act', {}):
            value = {**value, 'act': {**value['act'], 'arguments': json.dumps(value['act']['arguments'])}}
        if isinstance(value.get('say'), str):   # the tests write plain words; the decision writes parts
            value = {**value, 'say': [{'feeling': 'happy', 'text': value['say']}]}
        return types.SimpleNamespace(usage=None, choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(content=json.dumps(value, ensure_ascii=False)))])

    def respond(self, value):
        self.create.return_value = self.reply(value)

    def sequence(self, *values):
        self.create.side_effect = [self.reply(v) for v in values]

    def go_tool(self):
        self.env.tools.append(types.SimpleNamespace(id='game_go', info=types.SimpleNamespace(raw_schema={
            'name': 'game_go', 'description': 'go', 'parameters': {'type': 'object', 'required': ['x', 'z'],
                'properties': {'x': {'type': 'integer'}, 'z': {'type': 'integer'}}}})))
        self.env.meta['game_go'] = {'ciel/role': 'act', 'ciel/target_binding': {
            'kind': 'axes', 'point': True, 'fields': {'x': ['x', 0], 'z': ['z', 0]}}}

    async def say(self, text):
        return await self.decision.handle(llm.ChatMessage(role='user', content=[text]),
                                          [{'role': 'system', 'content': 'system'}, {'role': 'user', 'content': text}],
                                          [{'type': 'function', 'function': {'name': 'say_hi', 'parameters': {}}}], note='game')

    async def test_speaking_only_returns_the_words_and_starts_nothing(self):
        self.respond({'say': 'えへへ', 'act': {'kind': 'none'}})
        self.assertEqual(await self.say('えらいね'), '[happy]えへへ')
        self.runner.start.assert_not_awaited()
        self.env.use.assert_not_awaited()
        sent = self.create.await_args.kwargs
        # The conversation model's request as is, then how to decide, after the conversation
        self.assertEqual(sent['messages'][:2], [{'role': 'system', 'content': 'system'}, {'role': 'user', 'content': 'えらいね'}])
        self.assertTrue(sent['messages'][-1]['content'].startswith('game\n\ndecide\n- none'))
        if game_decision.models.is_local('mind'):
            self.assertEqual((sent['tools'][0]['function']['name'], sent['tool_choice']), ('say_hi', 'none'))
        else:
            self.assertNotIn('tools', sent)
            self.assertNotIn('tool_choice', sent)
        self.assertEqual(list(sent['response_format']['json_schema']['schema']['properties']), ['act', 'say'])

    async def test_a_work_is_started_with_the_decided_request(self):
        self.respond({'say': '作りますね', 'act': {'kind': 'work', 'request': '家を作る'}})
        self.assertEqual(await self.say('いいよ、お願い'), '[happy]作りますね')
        self.assertEqual(self.runner.start.await_args.args, ('game.goal', {'request': '家を作る'}))
        self.assertEqual(self.runner.start.await_args.kwargs['seconds'], 120)

    async def test_provider_action_request_keeps_json_authority(self):
        for local in (False, True):
            with self.subTest(local=local), patch('game_decision.models.is_local', return_value=local), \
                    patch('game_decision.models.options', side_effect=lambda role, **kw: kw):
                self.respond({'say': '集めます', 'act': {'kind': 'work', 'request': '原木を集める'}})
                await self.say('原木を集めて' + str(local))
                sent = self.create.await_args.kwargs
                self.assertEqual('tools' in sent, local)
                self.assertEqual('tool_choice' in sent, local)
                action = sent['response_format']['json_schema']['schema']['properties']['act']
                jsonschema.validate({'kind': 'work', 'request': '原木を集める'}, action)
        self.assertEqual(self.runner.start.await_count, 2)

    async def test_a_direct_action_is_used_and_a_refusal_is_told_in_her_words(self):
        self.respond({'say': '行きますね', 'act': {'kind': 'game_come', 'arguments': {}}})
        self.assertEqual(await self.say('来て'), '[happy]行きますね')
        self.assertEqual(self.env.use.await_args.args, ('game_come', {}))
        self.env.use.return_value = {'status': 'busy'}
        self.sequence({'say': '行きますね', 'act': {'kind': 'game_come', 'arguments': {}}},
                      {'say': 'ごめんなさい、今は動けないのです', 'act': {'kind': 'none'}})
        self.assertEqual(await self.say('来て'), '[happy]ごめんなさい、今は動けないのです')
        told = self.create.await_args.kwargs
        self.assertIn('できませんでした。理由：busy', told['messages'][-1]['content'])
        act_schema = told['response_format']['json_schema']['schema']['properties']['act']
        jsonschema.validate({'kind': 'none'}, act_schema)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate({'kind': 'game_come', 'arguments': '{}'}, act_schema)

    async def test_kinds_follow_the_work_state(self):
        kinds = lambda work: [a['properties']['kind']['const'] for a, _ in game_decision.acts(self.env, work)]
        self.assertEqual(kinds(None), ['none', 'work', 'game_come'])
        self.assertEqual(kinds({'state': 'running'}), ['none', 'tell', 'cancel', 'replace'])
        self.assertEqual(kinds({'state': 'needs_decision', 'decision': {'actions': ['reply', 'cancel'], 'message': 'q'}}),
                         ['none', 'reply', 'cancel', 'replace'])
        self.assertEqual(kinds({'state': 'cancelling'}), ['none'])

    async def test_an_ended_work_is_started_again_with_its_own_request(self):
        self.runner.work = {'state': 'failed', 'reason': 'deadline', 'capability': 'game.goal', 'arguments': {'request': '農場を作って'}}
        kinds = [a['properties']['kind']['const'] for a, _ in game_decision.acts(self.env, self.runner.work)]
        self.assertEqual(kinds, ['none', 'resume', 'work', 'game_come'])
        self.respond({'say': '続きをやりますね', 'act': {'kind': 'resume'}})
        self.assertEqual(await self.say('ツルハシを渡したよ、続けて'), '[happy]続きをやりますね')
        self.assertEqual(self.runner.start.await_args.args, ('game.goal', {'request': '農場を作って'}))
        self.runner.work = {'state': 'succeeded', 'capability': 'game.goal', 'arguments': {'request': 'x'}}
        self.assertNotIn('resume', [a['properties']['kind']['const'] for a, _ in game_decision.acts(self.env, self.runner.work)])

    async def test_words_and_answers_go_to_the_work(self):
        self.runner.work = {'state': 'running'}
        self.respond({'say': '伝えますね', 'act': {'kind': 'tell'}})
        await self.say('刈ってね')
        self.assertEqual(self.runner.tell.await_args.args, ('刈ってね',))
        self.runner.work = {'state': 'needs_decision', 'decision': {'decision_id': 'd', 'actions': ['retry', 'cancel']}}
        self.respond({'say': 'もう一度', 'act': {'kind': 'retry'}})
        await self.say('もう一回')
        self.assertEqual(self.runner.answer.await_args.args, ('d', 'retry', None))

    async def test_a_failed_decision_lets_the_conversation_model_answer(self):
        self.create.side_effect = TimeoutError()
        self.assertIsNone(await self.say('こんにちは'))
        self.runner.start.assert_not_awaited()

    async def test_stop_words_stop_at_once_and_she_says_it(self):
        with patch.object(self.decision, '_stop', AsyncMock(return_value={'message': '停止しました。'})) as stop:
            self.respond({'say': '止まりました！', 'act': {'kind': 'none'}})
            self.assertEqual(await self.say('止まって'), '[happy]止まりました！')
            stop.assert_awaited_once()
            self.assertIn('結果：停止しました。', self.create.await_args.kwargs['messages'][-1]['content'])
            self.create.side_effect = TimeoutError()
            self.assertEqual(await self.say('止まって'), '停止しました。')   # without the model, the fact itself

    def test_only_work_that_takes_the_request_is_offered(self):
        self.assertEqual([c['name'] for c in game_decision.capabilities(self.env)], ['game.goal'])
        self.env.profile['work']['capabilities'][0]['preparation'] = {'version': 1}
        self.assertEqual(game_decision.capabilities(self.env), [])
        self.assertNotIn('work', [a['properties']['kind']['const'] for a, _ in game_decision.acts(self.env, None)])

    async def test_a_cloud_model_is_asked_for_the_schema_and_its_answer_is_checked(self):
        with patch('models.is_local', return_value=False):
            self.respond({'say': 'こんにちは', 'act': {'kind': 'none'}})
            self.assertEqual(await self.say('こんにちは'), '[happy]こんにちは')
            sent = self.create.await_args.kwargs
            self.assertNotIn('temperature', sent)
            self.assertIn('reasoning_effort', sent)
            self.assertTrue(sent['response_format']['json_schema']['strict'])
            self.respond({'say': 'x', 'act': {'kind': 'fly_away'}})   # not one of the kinds
            self.assertIsNone(await self.say('飛んで'))
            self.env.use.assert_not_awaited()

    async def test_a_stop_word_stops_when_heard_and_only_for_the_owner(self):
        with patch.object(self.decision, '_stop', AsyncMock(return_value={'message': '停止しました。'})) as stop:
            before = self.decision._generation
            self.decision.on_transcribed(types.SimpleNamespace(transcript='止まって', is_final=True, item_id='i'), owner=False)
            stop.assert_not_awaited()
            self.decision.on_transcribed(types.SimpleNamespace(transcript='止まって', is_final=True, item_id='i'))
            await self.decision._fast_stop
            stop.assert_awaited_once()
            self.assertEqual(self.decision._generation, before + 1)

    async def test_an_action_aimed_at_named_coordinates_gets_the_bound_target(self):
        self.go_tool()
        kinds = lambda text: [a['properties']['kind']['const'] for a, _ in
                              game_decision.acts(self.env, None, game_decision.bind_targets(self.env, text, None, 'r'))]
        self.assertNotIn('game_go', kinds('あっちへ行って'))   # no target in the words: not offered
        self.assertIn('game_go', kinds('x 10 z -4 へ行って'))
        self.respond({'say': '向かいますね', 'act': {'kind': 'game_go', 'arguments': {'target_id': 'T1'}}})
        self.assertEqual(await self.say('x 10 z -4 へ行って'), '[happy]向かいますね')
        self.assertEqual(self.env.use.await_args.args, ('game_go', {'x': 10, 'z': -4}))


    async def test_what_was_pointed_at_goes_with_the_work_only_when_the_game_takes_it(self):
        pointed = '11111111-1111-4111-8111-111111111111'
        self.env.profile['reference_context'] = True
        self.env._refresh = AsyncMock(return_value=True)
        self.env.state = {'references': {'selection_id': pointed, 'points': [{'x': 1, 'y': 64, 'z': 2}], 'source': 'owner_gaze'}}
        self.respond({'say': '掘りますね', 'act': {'kind': 'work', 'request': 'あそこを掘って'}})
        await self.say('あそこを掘って')
        self.assertEqual(self.runner.start.await_args.args, ('game.goal', {'request': 'あそこを掘って'}))   # not declared
        self.env.profile['work']['capabilities'][0]['handoff'] = {**HANDOFF, 'reference_argument': 'reference'}
        await self.say('あそこを掘って')
        self.assertEqual(self.runner.start.await_args.args, ('game.goal', {'request': 'あそこを掘って', 'reference': pointed}))
        await self.say('x 10 z -4 を掘って')   # coordinates in the words: the pointing is not used
        self.assertEqual(self.runner.start.await_args.args, ('game.goal', {'request': 'あそこを掘って'}))
        # A restart later is the same request, without the id of a pointing that has passed
        self.runner.work = {'state': 'failed', 'reason': 'deadline', 'capability': 'game.goal',
                            'arguments': {'request': 'あそこを掘って', 'reference': pointed}}
        self.assertNotIn(pointed, json.dumps(game_decision.acts(self.env, self.runner.work), ensure_ascii=False))
        self.respond({'say': '続けますね', 'act': {'kind': 'resume'}})
        await self.say('続けて')
        self.assertEqual(self.runner.start.await_args.args, ('game.goal', {'request': 'あそこを掘って'}))


class AfterWorkTest(unittest.TestCase):
    def test_ciel_may_act_after_a_work_ended_unless_the_owner_stopped_it(self):
        from game_decision import after_work
        self.assertTrue(after_work(None))
        for state, reason in [('succeeded', ''), ('failed', 'stalled'), ('cancelled', 'deadline'),
                              ('cancelled', 'execution_error')]:
            self.assertTrue(after_work({'state': state, 'reason': reason}), (state, reason))
        for state, reason in [('cancelled', 'stopped'), ('cancelled', 'owner_no_answer'), ('running', ''),
                              ('needs_decision', 'owner_question')]:
            self.assertFalse(after_work({'state': state, 'reason': reason}), (state, reason))


class SayTest(unittest.TestCase):
    def test_each_part_is_led_by_its_feeling_and_stray_marks_are_taken_out(self):
        self.assertEqual(game_decision.spoken([{'feeling': 'happy', 'text': '[relaxed]わあ！'},
                                               {'feeling': 'thinking', 'text': 'ええと、'}, {'feeling': 'sad', 'text': '  '}]),
                         '[happy]わあ！[thinking]ええと、')
        self.assertEqual(game_decision.spoken('words without parts'), '')
        feelings = game_decision.SAY['items']['properties']['feeling']['enum']
        self.assertIn('neutral', feelings)
        self.assertIn('jitome', feelings)


if __name__ == '__main__':
    unittest.main()


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

    async def test_active_stopped_and_confirmation_only_allow_speech(self):
        # 失敗・期限切れの作業のあとは、自分で次の一手を始めてよい（2026-11-21）。持ち主が止めたあとは動かない
        for state in ('running', 'accepted', 'needs_decision', 'cancelling', 'cancelled', 'unknown'):
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
