import json
import types
import unittest
from unittest.mock import AsyncMock, patch

from livekit.agents import llm

import game_decision
from game_decision import GameDecision
from game_intake import GameIntake

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
        self.intake = GameIntake(self.runner, 'i', client=client)
        self.decision = GameDecision(self.intake, 'decide\n{actions}')

    @staticmethod
    def reply(value):
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
        return await self.decision.handle(llm.ChatMessage(role='user', content=[text]), 'system', [{'role': 'user', 'content': text}])

    async def test_speaking_only_returns_the_words_and_starts_nothing(self):
        self.respond({'say': 'えへへ', 'act': {'kind': 'none'}})
        self.assertEqual(await self.say('えらいね'), 'えへへ')
        self.runner.start.assert_not_awaited()
        self.env.use.assert_not_awaited()
        sent = self.create.await_args.kwargs
        self.assertTrue(sent['messages'][0]['content'].startswith('system\n\ndecide\n- none'))
        self.assertEqual(list(sent['response_format']['json_schema']['schema']['properties']), ['say', 'act'])

    async def test_a_work_is_started_with_the_decided_request(self):
        self.respond({'say': '作りますね', 'act': {'kind': 'work', 'request': '家を作る'}})
        self.assertEqual(await self.say('いいよ、お願い'), '作りますね')
        self.assertEqual(self.runner.start.await_args.args, ('game.goal', {'request': '家を作る'}))
        self.assertEqual(self.runner.start.await_args.kwargs['seconds'], 120)

    async def test_a_direct_action_is_used_and_a_refusal_is_told_in_her_words(self):
        self.respond({'say': '行きますね', 'act': {'kind': 'game_come', 'arguments': {}}})
        self.assertEqual(await self.say('来て'), '行きますね')
        self.assertEqual(self.env.use.await_args.args, ('game_come', {}))
        self.env.use.return_value = {'status': 'busy'}
        self.sequence({'say': '行きますね', 'act': {'kind': 'game_come', 'arguments': {}}},
                      {'say': 'ごめんなさい、今は動けないのです', 'act': {'kind': 'none'}})
        self.assertEqual(await self.say('来て'), 'ごめんなさい、今は動けないのです')
        told = self.create.await_args.kwargs
        self.assertIn('できませんでした。理由：busy', told['messages'][0]['content'])
        self.assertEqual(told['response_format']['json_schema']['schema']['properties']['act']['anyOf'], [game_decision.NONE])

    async def test_kinds_follow_the_work_state(self):
        kinds = lambda work: [a['properties']['kind']['const'] for a, _ in game_decision.acts(self.env, work)]
        self.assertEqual(kinds(None), ['none', 'work', 'game_come'])
        self.assertEqual(kinds({'state': 'running'}), ['none', 'tell', 'cancel'])
        self.assertEqual(kinds({'state': 'needs_decision', 'decision': {'actions': ['reply', 'cancel'], 'message': 'q'}}),
                         ['none', 'reply', 'cancel'])
        self.assertEqual(kinds({'state': 'cancelling'}), ['none'])

    async def test_an_ended_work_is_started_again_with_its_own_request(self):
        self.runner.work = {'state': 'failed', 'reason': 'deadline', 'capability': 'game.goal', 'arguments': {'request': '農場を作って'}}
        kinds = [a['properties']['kind']['const'] for a, _ in game_decision.acts(self.env, self.runner.work)]
        self.assertEqual(kinds, ['none', 'resume', 'work', 'game_come'])
        self.respond({'say': '続きをやりますね', 'act': {'kind': 'resume'}})
        self.assertEqual(await self.say('ツルハシを渡したよ、続けて'), '続きをやりますね')
        self.assertEqual(self.runner.start.await_args.args, ('game.goal', {'request': '農場を作って'}))
        self.runner.work = {'state': 'succeeded', 'capability': 'game.goal', 'arguments': {'request': 'x'}}
        self.assertNotIn('resume', [a['properties']['kind']['const'] for a, _ in game_decision.acts(self.env, self.runner.work)])

    async def test_words_and_answers_go_to_the_work(self):
        self.runner.work = {'state': 'running'}
        self.respond({'say': '伝えますね', 'act': {'kind': 'tell', 'message': '刈ってね'}})
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
        with patch.object(self.intake, '_stop', AsyncMock(return_value={'message': '停止しました。'})) as stop:
            self.respond({'say': '止まりました！', 'act': {'kind': 'none'}})
            self.assertEqual(await self.say('止まって'), '止まりました！')
            stop.assert_awaited_once()
            self.assertIn('結果：停止しました。', self.create.await_args.kwargs['messages'][0]['content'])
            self.create.side_effect = TimeoutError()
            self.assertEqual(await self.say('止まって'), '停止しました。')   # without the model, the fact itself

    def test_games_whose_work_needs_preparation_stay_with_the_intake(self):
        self.env.profile['reference_context'] = True   # pointing alone does not hand the game to the intake
        self.assertTrue(game_decision.supported(self.env))
        self.env.profile['work']['capabilities'][0]['preparation'] = {'version': 1}
        self.assertFalse(game_decision.supported(self.env))

    async def test_an_action_aimed_at_named_coordinates_gets_the_bound_target(self):
        self.go_tool()
        kinds = lambda text: [a['properties']['kind']['const'] for a, _ in
                              game_decision.acts(self.env, None, game_decision.bind_targets(self.env, text, None, 'r'))]
        self.assertNotIn('game_go', kinds('あっちへ行って'))   # no target in the words: not offered
        self.assertIn('game_go', kinds('x 10 z -4 へ行って'))
        self.respond({'say': '向かいますね', 'act': {'kind': 'game_go', 'arguments': {'target_id': 'T1'}}})
        self.assertEqual(await self.say('x 10 z -4 へ行って'), '向かいますね')
        self.assertEqual(self.env.use.await_args.args, ('game_go', {'x': 10, 'z': -4}))


if __name__ == '__main__':
    unittest.main()
