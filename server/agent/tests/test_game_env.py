"""ゲームの環境（game_env.py）と、心の振り分け・道具（mind.py）。ゲームは試験用の小さなゲーム（tests/fake_game.py）で、
会話サーバーがゲームの名前・技の名前を知らずに動くかを確かめる"""
import asyncio
import json
import types
import unittest
from unittest import mock

from livekit.agents import llm

import board
import game_env
import goals
import mind
import tools
from conversation import Conversation
from tests.fake_game import FakeGame


class Said:
    def __init__(self):
        self.calls = []

    def __call__(self, why, *, settle, instructions, merge=False):
        self.calls.append((why, settle, instructions))

    def lines(self):
        return [c[2] for c in self.calls]


class Diary:
    def __init__(self):
        self.added = []

    def add(self, kind, text):
        self.added.append((kind, text))


def packet(on, topic='ciel.game'):
    return types.SimpleNamespace(topic=topic, data=json.dumps({'v': 1, 'type': 'game.link', 'on': on}).encode('utf-8'))


def ctx_with(text):
    ctx = llm.ChatContext()
    ctx.add_message(role='system', content='会話の指示')
    ctx.add_message(role='user', content=text)
    return ctx


async def until(fn, seconds=2.0):
    for _ in range(int(seconds / 0.01)):
        if fn():
            return
        await asyncio.sleep(0.01)
    raise AssertionError('待っても変わらなかった')


class EnvCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fake = FakeGame()
        self.env = game_env.GameEnv('test', 'http://unused', connect=lambda env: self.fake.connect(env))
        self.said, self.shown, self.diary, self.board = Said(), [], Diary(), board.Board()
        self.env.say, self.env.notify, self.env.diary, self.env.board = self.said, self.shown.append, self.diary, self.board
        self.assertTrue(await self.env.prepare())

    async def asyncTearDown(self):
        await self.env.close()

    async def link(self):
        self.env.on_data(packet(True))
        await until(lambda: self.env.linked)


class PrepareTest(EnvCase):
    async def test_profile_tools_prompt_and_seeds_are_read(self):
        env = self.env
        self.assertEqual(env.label, 'テスト')
        self.assertEqual(env.instructions, 'テストの遊び方：跳ぶときは test_jump。')
        # 心に渡すのは act・look・know だけ。名前の頭がゲームの名前でない道具は使わない
        self.assertEqual({t.id for t in env.tools}, {'test_jump', 'test_stop', 'test_look', 'test_facts'})
        self.assertEqual(env.tool_ids('act'), {'test_jump', 'test_stop'})
        self.assertIn(('ちょっと跳んでみて', 'test_jump'), env.seeds())
        self.assertIn(('宝箱を作っておいて', 'start_goal'), env.seeds())
        self.assertIn(('えらいね', None), env.seeds())
        self.assertEqual(env.from_comments(), {'test_jump': False, 'test_stop': False, 'test_look': False, 'test_facts': True})

    async def test_unreachable_game_is_not_ready(self):
        class Down:
            async def __aenter__(self):
                raise OSError('down')

            async def __aexit__(self, *a):
                return False
        env = game_env.GameEnv('test', 'http://unused', connect=lambda env: Down())
        with mock.patch.object(game_env, 'PREPARE_TIMEOUT', 0.2):
            self.assertFalse(await env.prepare())
        await env.close()


class LinkTest(EnvCase):
    async def test_app_switch_links_shows_state_and_unlinks(self):
        env = self.env
        self.assertEqual(await env.use('test_jump', {}), {'status': 'unavailable'})   # 受け持つ前は動かさない
        self.assertEqual((await env.use('test_facts', {}))['fact'], '宝箱は板 8 枚')    # 知識は受け持たなくても調べられる
        env.on_data(packet(True, topic='ciel.style'))   # ほかの知らせでは動かない
        self.assertFalse(env.wanted)
        await self.link()
        self.assertTrue(env.playing())
        self.assertEqual(self.shown[-1], {'v': 1, 'type': 'game.state', 'linked': True, 'in_world': True, 'reason': ''})
        self.assertEqual(env.context(), '[テストの様子]\nシエル：元気')
        # 様子が変わったという知らせで読み直す
        await self.fake.changed(text='シエル：疲れた')
        await until(lambda: 'シエル：疲れた' in env.context())
        env.on_data(packet(False))
        await until(lambda: not env.linked)
        self.assertEqual(self.shown[-1]['reason'], 'off')
        self.assertIn('つながっていない', env.context())

    async def test_busy_is_shown(self):
        self.fake.busy = True
        self.env.on_data(packet(True))
        await until(lambda: self.shown and self.shown[-1]['reason'] == 'busy')
        self.assertFalse(self.env.linked)

    def test_server_without_a_game_refuses(self):
        shown = []
        on_data = game_env.refuse(shown.append)
        on_data(packet(False))
        self.assertEqual(shown, [])
        on_data(packet(True))
        self.assertEqual(shown[-1]['reason'], 'unavailable')


class EventTest(EnvCase):
    async def test_long_skills_become_cards_closed_by_the_end_notice(self):
        await self.link()
        r = await self.env.use('test_jump', {'height': 3})
        self.assertEqual(r['status'], 'started')
        self.assertIn('3 だけ跳ぶ：実行中', self.board.context())
        failed = {'kind': 'task_done', 'task': 7, 'title': '3 だけ跳ぶ', 'ok': False, 'failed': True, 'card': 'failed',
                  'card_note': '鍵が無い', 'say': '[テスト：「3 だけ跳ぶ」ができなかった。理由：鍵が無い]'}
        await self.fake.emit(failed)
        await until(lambda: self.said.calls)
        self.assertIn('3 だけ跳ぶ：失敗', self.board.context())
        self.assertEqual(self.said.lines()[-1], '[テスト：「3 だけ跳ぶ」ができなかった。理由：鍵が無い。同じ頼みでうまくいかなかったのは 1 回目]')
        await self.fake.emit(failed)
        await until(lambda: len(self.said.calls) == 2)
        self.assertIn('2 回目', self.said.lines()[-1])   # 同じ頼みの何回目かは、会話サーバーが題で数える

    async def test_urgency_limits_and_the_diary(self):
        await self.link()
        hurt = {'kind': 'hurt', 'urgency': 'urgent', 'key': 'hurt', 'say': '[テスト：痛い]'}
        await self.fake.emit(hurt)
        await self.fake.emit(hurt)   # 同じ種類は、しばらく 1 回まで
        await self.fake.emit({'kind': 'won', 'urgency': 'normal', 'key': 'won', 'say': '[テスト：勝った]', 'memorable': 'テストで勝った'})
        await self.fake.emit({'kind': 'won2', 'urgency': 'ambient', 'key': 'w2', 'say': '[言わない]', 'memorable': 'テストで勝った'})
        await until(lambda: len(self.said.calls) == 2)
        await asyncio.sleep(0.05)
        self.assertEqual([(c[1], c[2]) for c in self.said.calls],
                         [(game_env.URGENT_SETTLE, '[テスト：痛い]'), (game_env.SETTLE, '[テスト：勝った]')])
        self.assertEqual(self.diary.added, [('test', 'テストで勝った')])   # 同じことは 1 度だけ

    async def test_the_view_goes_to_the_eyes(self):
        await self.link()
        seen = []

        class Eyes:
            def see_game(self, data, note, place):
                seen.append((data[:3], note, place))
                return types.SimpleNamespace(id=4)
        self.env.eyes = Eyes()
        r = await self.env.use('test_look', {})
        self.assertEqual(r['view'], 4)
        self.assertIn('#4', r['note'])
        self.assertEqual(seen, [(b'\xff\xd8\xff', '北を向いている', 'テスト')])


class GoalsAdapterTest(EnvCase):
    async def test_the_runner_plans_runs_checks_and_repairs_through_the_game(self):
        await self.link()
        self.fake.steps = [{'ok': False, 'reason': 'no_key', 'complete': False, 'why_short': '鍵が無い'},
                           {'ok': True, 'complete': True, 'progress': None},
                           {'ok': True, 'complete': True, 'progress': None}]
        self.fake.repairs = [{'steps': [{'kind': 'find', 'args': {'item': 'key'}, 'label': '鍵を探す', 'progress': None},
                                        {'kind': 'make', 'args': {'item': 'chest'}, 'label': '宝箱を作る', 'progress': None}],
                              'text': '鍵が無いので、探す段を足した'}]
        runner = goals.GoalRunner(Said())
        runner.register('test', game_env.GoalsAdapter(self.env), 'テスト')
        r = await runner.start('test', '宝箱を作る', {'make': 'chest'})
        self.assertEqual(r['steps'], ['宝箱を作る'])
        await until(lambda: runner.goal.status == 'done')
        self.assertEqual(runner.state()['changes'], ['鍵が無いので、探す段を足した'])
        steps = [a['step']['label'] for n, a in self.fake.calls if n == 'test_goal_step']
        self.assertEqual(steps, ['宝箱を作る', '鍵を探す', '宝箱を作る'])
        await runner.stop()


class MindGameTest(EnvCase):
    def setUp(self):
        patcher = mock.patch('clock.now_line', return_value='[今：朝]')
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_game_words_go_to_the_mind_only_while_linked(self):
        m = mind.Mind(Conversation(), body=self.env)
        self.assertEqual(m.route(ctx_with('跳んでみて'), {'seconds': 1.0}), 'talker')
        await self.link()
        self.assertEqual(m.route(ctx_with('跳んでみて'), {'seconds': 1.0}), 'mind')
        self.assertEqual(m.route(ctx_with('うまくできてる'), {'seconds': 1.0}), 'talker')
        self.assertEqual(mind.Mind(Conversation()).route(ctx_with('跳んでみて'), {'seconds': 1.0}), 'talker')

    async def test_game_tools_only_while_linked_and_one_moving_call(self):
        m = mind.Mind(Conversation(), body=self.env)
        all_tools = tools.TOOLS + self.env.tools
        ids = lambda: {t.id for t in m.tools_for(ctx_with('跳んで'), all_tools)}   # noqa: E731
        self.assertFalse({'test_jump', 'test_facts', 'start_goal'} & ids())
        await self.link()
        self.assertTrue({'test_jump', 'test_look', 'test_facts', 'start_goal'} <= ids())
        self.assertIn('test_jump', m.moving_calls())
        self.assertNotIn('test_look', m.moving_calls())
        self.assertIn('test_facts', m.game_calls())
        self.assertIn('add_subgoal', m.one_call_tools())

    async def test_the_state_goes_to_the_talker_and_the_mind(self):
        await self.link()
        m = mind.Mind(Conversation(), body=self.env)
        ctx = ctx_with('今どんな感じ？')
        for built in (m.build(ctx, turn={}), m.build(ctx, talker_instructions='短い指示', turn={})):
            self.assertTrue(any('[テストの様子]' in (i.text_content or '') for i in built.items))

    async def test_moving_the_body_is_not_for_comments(self):
        with mock.patch.dict(tools.GAME_FROM_COMMENTS, self.env.from_comments()):
            allowed = {t.id for t in tools.for_comments(tools.TOOLS + self.env.tools)}
        self.assertIn('test_facts', allowed)
        self.assertNotIn('test_jump', allowed)


class NoGameNamesTest(unittest.TestCase):
    def test_the_conversation_server_does_not_know_the_game(self):
        # 会話サーバーのコードに、ゲームの名前を書かない（ゲームの側が持つ。docs/game-environment-mcp-design-ja.md の 5.4）。
        # 見るのはコードの名前と短い文字列（'minecraft' のような値）。コメント・説明の文・文書への参照は見ない
        import ast
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent
        files = [p for p in root.glob('*.py') if not p.name.startswith(('bench_', 'eval_'))] + list((root / 'tools').glob('*.py'))
        found = []
        for p in files:
            tree = ast.parse(p.read_text(encoding='utf-8'))
            docs = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}
            for n in ast.walk(tree):
                words = ([n.id] if isinstance(n, ast.Name) else [n.attr] if isinstance(n, ast.Attribute)
                         else [n.name] if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                         else [n.value] if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs
                         and len(n.value) < 40 else [])
                if any('minecraft' in w.lower() or 'マイクラ' in w for w in words):
                    found.append(f'{p.name}:{n.lineno}')
        self.assertEqual(found, [])


if __name__ == '__main__':
    unittest.main()
