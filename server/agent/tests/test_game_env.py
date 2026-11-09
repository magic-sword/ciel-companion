"""ゲームの環境（game_env.py）と、心の振り分け・道具（mind.py）。ゲームは試験用の小さなゲーム（tests/fake_game.py）で、
会話サーバーがゲームの名前・技の名前を知らずに動くかを確かめる"""
import asyncio
import json
import types
import unittest
from unittest import mock

from livekit.agents import llm

import board
import activity
import game_env
import goals
import mind
import tools
from conversation import Conversation
from tests.fake_game import FakeGame


class Said:
    def __init__(self):
        self.calls = []

    def __call__(self, why, *, settle, instructions, merge=False, reaction_kind=None, reaction_event=None):
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
    async def asyncSetUp(self):
        timers = mock.patch.multiple(game_env, LINK_RETRY_SECONDS=.03, PING_SECONDS=.05, RETRY_MIN=.01)
        timers.start()
        self.addCleanup(timers.stop)
        await super().asyncSetUp()

    async def test_busy_retries_automatically_when_previous_owner_leaves(self):
        self.fake.busy = True
        with mock.patch.object(game_env, 'LINK_RETRY_SECONDS', .03):
            self.env.on_data(packet(True))
            await until(lambda: self.env.reason == 'busy')
            self.fake.busy = False
            await until(lambda: self.env.linked)
        self.assertTrue(self.env.playing())

    async def test_busy_wait_does_not_flicker_or_retry_after_off(self):
        self.fake.busy = True
        with mock.patch.object(game_env, 'LINK_RETRY_SECONDS', .02):
            self.env.on_data(packet(True))
            await until(lambda: self.env.reason == 'busy')
            self.shown.clear()
            await asyncio.sleep(.10)
            self.assertEqual(self.env.reason, 'busy')
            self.assertEqual(self.shown, [])
            self.env.on_data(packet(False))
            await until(lambda: self.env.reason == 'off')
            count = len(self.fake.calls)
            await asyncio.sleep(.08)
            self.assertEqual(len(self.fake.calls), count)

    async def test_unclaimed_transport_is_kept_alive_without_claiming_body(self):
        with mock.patch.object(game_env, 'LINK_RETRY_SECONDS', .01), mock.patch.object(game_env, 'PING_SECONDS', .02):
            # Recreate the monitor to set its initial ping deadline with the short interval.
            self.env._reconnect(self.env._session)
            previous = self.env._session
            with mock.patch.object(game_env, 'RETRY_MIN', .01):
                await until(lambda: self.env._session is not None and self.env._session is not previous)
                session = self.env._session
                session.send_ping = mock.AsyncMock()
                await until(lambda: session.send_ping.await_count > 0)
        self.assertFalse(self.env.linked)
        self.assertNotIn(('test_link', {'on': True}), self.fake.calls)

    async def test_failed_ping_recreates_transport_and_reclaims_if_wanted(self):
        await self.link()
        session = self.env._session
        with mock.patch.object(game_env, 'LINK_RETRY_SECONDS', .01), mock.patch.object(game_env, 'PING_SECONDS', .02), mock.patch.object(game_env, 'RETRY_MIN', .01):
            self.env._reconnect(session)
            await until(lambda: self.env._session is not None and self.env._session is not session and self.env.linked)
            second = self.env._session
            second.send_ping = mock.AsyncMock(side_effect=ConnectionError('lost'))
            await until(lambda: self.env._session is not None and self.env._session is not second and self.env.linked)

    async def test_expired_session_on_manual_retry_is_replaced(self):
        from mcp.shared.exceptions import McpError
        from mcp.types import ErrorData
        await self.link()
        expired = self.env._session
        expired.call_tool = mock.AsyncMock(side_effect=McpError(ErrorData(code=32600, message='Session terminated')))
        with mock.patch.object(game_env, 'RETRY_MIN', .01):
            self.env.on_data(packet(True))
            await until(lambda: self.env._session is not None and self.env._session is not expired and self.env.linked)
        self.assertEqual(self.env.reason, '')

    async def test_off_during_slow_link_does_not_leave_body_claimed(self):
        entered, release = asyncio.Event(), asyncio.Event()
        original = self.env._call
        async def slow(name, args):
            if name == 'test_link' and args.get('on'):
                entered.set()
                await release.wait()
            return await original(name, args)
        self.env._call = slow
        self.env.on_data(packet(True))
        await entered.wait()
        self.env.on_data(packet(False))
        release.set()
        await until(lambda: self.env.reason == 'off')
        self.assertFalse(self.fake.linked)
        self.assertFalse(self.env.linked)

    async def test_app_switch_links_shows_state_and_unlinks(self):
        env = self.env
        self.assertEqual(await env.use('test_jump', {}), {'status': 'unavailable'})   # 受け持つ前は動かさない
        self.assertEqual((await env.use('test_facts', {}))['fact'], '宝箱は板 8 枚')    # 知識は受け持たなくても調べられる
        env.on_data(packet(True, topic='ciel.style'))   # ほかの知らせでは動かない
        self.assertFalse(env.wanted)
        await self.link()
        self.assertTrue(env.playing())
        self.assertEqual(self.shown[-1], {'v': 1, 'type': 'game.state', 'linked': True, 'in_world': True, 'reason': ''})   # 以前のアプリへ
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

    async def test_env_list_and_env_link_name_the_game(self):
        self.assertEqual(game_env.listing(self.env), {'v': 1, 'type': 'env.list', 'games': [{'game': 'test', 'label': 'テスト'}]})
        self.assertEqual(game_env.listing(None)['games'], [])
        other = types.SimpleNamespace(topic='ciel.game', data=json.dumps({'type': 'env.link', 'game': 'other', 'on': True}).encode())
        self.env.on_data(other)   # ほかのゲームのスイッチでは動かない
        self.assertFalse(self.env.wanted)
        self.env.on_data(types.SimpleNamespace(topic='ciel.game', data=json.dumps({'type': 'env.link', 'game': 'test', 'on': True}).encode()))
        await until(lambda: self.env.linked)
        states = [m for m in self.shown if m['type'] == 'env.state']
        self.assertEqual(states[-1], {'v': 1, 'type': 'env.state', 'game': 'test', 'label': 'テスト', 'linked': True,
                                      'playing': True, 'reason': ''})

    def test_server_without_a_game_refuses(self):
        shown = []
        on_data = game_env.refuse(shown.append)
        on_data(packet(False))
        self.assertEqual(shown, [])
        on_data(packet(True))
        self.assertEqual(shown[-1]['reason'], 'unavailable')
        on_data(types.SimpleNamespace(topic='ciel.game', data=json.dumps({'type': 'env.link', 'game': 'x', 'on': True}).encode()))
        self.assertEqual([m['type'] for m in shown[-2:]], ['env.state', 'game.state'])


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
        await self.fake.emit({**failed, 'task': 8})
        await until(lambda: len(self.said.calls) == 2)
        self.assertIn('2 回目', self.said.lines()[-1])   # 同じ頼みの何回目かは、会話サーバーが題で数える

    async def test_urgency_limits_and_the_diary(self):
        await self.link()
        hurt = {'event_id': 'same-hurt', 'kind': 'hurt', 'urgency': 'urgent', 'key': 'hurt', 'say': '[テスト：痛い]'}
        await self.fake.emit(hurt)
        await self.fake.emit(hurt)   # 同じ種類は、しばらく 1 回まで
        await self.fake.emit({'kind': 'won', 'urgency': 'normal', 'key': 'won', 'say': '[テスト：勝った]', 'memorable': 'テストで勝った'})
        await self.fake.emit({'kind': 'won2', 'urgency': 'ambient', 'key': 'w2', 'say': '[言わない]', 'memorable': 'テストで勝った'})
        await until(lambda: len(self.said.calls) == 2)
        await asyncio.sleep(0.05)
        self.assertEqual([(c[1], c[2]) for c in self.said.calls],
                         [(game_env.URGENT_SETTLE, '[テスト：痛い]'), (game_env.SETTLE, '[テスト：勝った]')])
        self.assertEqual(self.diary.added, [('test', 'テストで勝った')])   # 同じことは 1 度だけ
        self.env.linked = False
        self.env.on_event({'kind': 'died', 'memorable': '未所有の体の記憶', 'say': '[old]', 'urgency': 'urgent'})
        self.assertEqual(self.diary.added, [('test', 'テストで勝った')])
        self.assertEqual(len(self.said.calls), 2)

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


class WorkContractTest(EnvCase):
    async def test_opaque_work_runs_over_actual_mcp_without_client_planning(self):
        await self.link()
        runner = goals.GoalRunner(self.said, env=self.env)
        self.env.goals = runner
        try:
            result = await runner.start('test.solve_puzzle', {'board': 'abc'}, constraints={'moves': 7})
            self.assertEqual(result['state'], 'running')
            self.assertEqual(runner.state()['v'], 2)
            self.assertNotIn('steps', runner.state())
            self.fake.work = {**self.fake.work, 'revision': 2, 'state': 'needs_decision',
                              'decision': {'decision_id': 'd'}, 'message': 'Need a decision'}
            await self.fake.emit({'kind': 'work_state', 'work': self.fake.work})
            await until(lambda: runner.work['state'] == 'needs_decision')
            self.assertEqual((await runner.answer('old', 'retry'))['reason'], 'stale_decision')
            await runner.stop()
            self.assertEqual(runner.work['state'], 'cancelled')
            self.assertFalse(any('_goal_' in name for name, args in self.fake.calls))
        finally:
            await runner.close()


class GoalHoldsBodyTest(EnvCase):
    async def test_direct_body_command_cannot_replace_owned_work(self):
        await self.link()
        stop = mock.AsyncMock()
        self.env.goals = types.SimpleNamespace(body_step=lambda: 'オークの原木を 2 個集める', stop=stop)
        r = await self.env.use('test_jump', {})
        self.assertEqual(r['status'], 'busy')
        stop.assert_not_awaited()
        stop.return_value = {'state': 'cancelled'}
        self.assertEqual((await self.env.use('test_stop', {}))['state'], 'cancelled')   # 止めるのはよい
        self.assertEqual((await self.env.use('test_look', {}))['status'], 'seen')      # 見るのはよい
        self.assertNotIn(('test_jump', {}), self.fake.calls)
        self.env.goals = types.SimpleNamespace(body_step=lambda: None)
        self.assertEqual((await self.env.use('test_jump', {}))['status'], 'started')


class BodyLifecycleTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = game_env.GameEnv('test', 'http://unused')
        self.env.linked = True
        self.env._body_protocol_valid = True
        self.env.board = board.Board()
        self.env.activity = activity.Activity(None)
        self.env.meta = {'test_jump': {'ciel/role': 'act', 'ciel/long_running': True}}

    async def test_old_body_format_is_rejected_without_reusing_old_snapshot(self):
        self.env._body = {'version': 1, 'session': 'old', 'revision': 9}
        for body in (None, {'version': 0}, {'version': 2}):
            state = {'linked': True, 'playing': True, 'doing': 'obsolete', 'body': body}
            self.env._session = types.SimpleNamespace(read_resource=mock.AsyncMock(return_value=types.SimpleNamespace(
                contents=[types.SimpleNamespace(text=json.dumps(state))])))
            await self.env._refresh()
            self.assertEqual(self.env._body, {})
            shown = self.env.activity.state()
            self.assertEqual(shown['body']['reason'], 'body_protocol_mismatch')
            self.assertNotIn('doing', shown)
            self.assertNotIn('tasks', shown)
            self.env._call = mock.AsyncMock()
            result = await self.env.use('test_jump', {})
            self.assertEqual(result['reason'], 'body_protocol_mismatch')
            self.env._call.assert_not_awaited()

    async def test_done_before_response_cannot_resurrect_two_finished_tasks(self):
        for task in (7, 8):
            async def call(name, args):
                self.env.on_event({'kind': 'task_done', 'task': task, 'title': 'follow', 'ok': False})
                return {'status': 'started', 'task': task, 'title': 'follow'}
            self.env._call = call
            result = await self.env.use('test_jump', {})
            self.assertEqual(result['status'], 'completed')
        self.assertEqual(self.env.activity._tasks, {})
        self.assertEqual(self.env._cards, {})

    async def test_duplicate_done_notifies_once_but_new_session_can_reuse_id(self):
        said = Said()
        self.env.say = said
        event = {'input_v': 1, 'event_id': 'done1', 'source_epoch': 'source', 'seq': 1,
                 'occurred_at': __import__('time').time(),
                 'kind': 'task_done', 'session': 'one', 'task': 1, 'title': 'follow', 'ok': True, 'say': '[done]'}
        self.env.on_event(event)
        self.env.on_event(event)
        self.env.on_event({**event, 'session': 'two', 'event_id': 'done2', 'seq': 2})
        self.assertEqual(len(said.calls), 2)

    async def test_unowned_last_snapshot_is_not_a_new_task_result(self):
        self.env._body = {'session': 'new', 'revision': 1, 'current': None,
            'last': {'id': 99, 'title': 'old task', 'result': {'ok': True}}}
        self.env._reconcile_body()
        self.assertEqual(self.env._completed, {})

    async def test_snapshot_repairs_missed_done_and_real_notice_still_reaches_mind(self):
        said = Said()
        self.env.say = said
        self.env._call = mock.AsyncMock(return_value={'status': 'accepted', 'session': 'one', 'task': 1, 'title': 'follow'})
        await self.env.use('test_jump', {})
        self.env._body = {'session': 'one', 'revision': 1, 'current': {'id': 1, 'title': 'follow', 'phase': 'running'}}
        self.env._reconcile_body()
        self.env._body = {'session': 'one', 'revision': 2, 'current': None,
                          'last': {'id': 1, 'title': 'follow', 'phase': 'failed', 'result': {'ok': False, 'reason': 'no_path'}}}
        self.env._reconcile_body()
        self.assertEqual(self.env._cards, {})
        self.assertEqual(self.env.activity.state()['body']['phase'], 'idle')
        self.env.on_event({'input_v': 1, 'event_id': 'failed1', 'source_epoch': 'source', 'seq': 1,
                           'occurred_at': __import__('time').time(),
                           'kind': 'task_done', 'session': 'one', 'task': 1, 'ok': False, 'failed': True, 'say': '[failed]'})
        self.assertEqual(len(said.calls), 1)

    async def test_old_refresh_cannot_overwrite_newer_revision(self):
        self.env._body = {'version': 1, 'session': 'one', 'epoch': 'boot', 'revision': 5}
        self.env.state = {'doing': 'new'}
        self.env._session = types.SimpleNamespace(read_resource=mock.AsyncMock(return_value=types.SimpleNamespace(contents=[
            types.SimpleNamespace(text=json.dumps({'doing': 'old', 'body': {'version': 1, 'session': 'one', 'epoch': 'boot', 'revision': 4}}))])))
        await self.env._refresh()
        self.assertEqual(self.env.state['doing'], 'new')

    async def test_search_is_not_blocked_by_body_submission(self):
        entered, release = asyncio.Event(), asyncio.Event()
        self.env.meta['test_search'] = {'ciel/role': 'know'}
        async def call(name, args):
            if name == 'test_jump':
                entered.set()
                await release.wait()
            return {'status': 'ok'}
        self.env._call = call
        task = asyncio.create_task(self.env.use('test_jump', {}))
        await entered.wait()
        result = await asyncio.wait_for(self.env.use('test_search', {}), .5)
        self.assertEqual(result['status'], 'ok')
        release.set()
        await task

    async def test_direct_command_cannot_overtake_planning_work(self):
        stop = mock.AsyncMock()
        self.env.goals = types.SimpleNamespace(body_step=lambda: 'planning', stop=stop)
        async def call(name, args):
            self.assertEqual(stop.await_count, 1)
            return {'status': 'accepted', 'task': 1}
        self.env._call = call
        result = await self.env.use('test_jump', {})
        self.assertEqual(result['status'], 'busy')
        stop.assert_not_awaited()

    async def test_spontaneous_action_cannot_replace_current_body_command(self):
        self.env.activity.thinking_origin = 'initiative'
        self.env._body = {'current': {'id': 1}}
        self.env._call = mock.AsyncMock()
        result = await self.env.use('test_jump', {})
        self.assertEqual(result['status'], 'goal_running')
        self.env._call.assert_not_awaited()


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
        self.assertFalse({'test_jump', 'test_facts', 'submit_game_task'} & ids())
        await self.link()
        self.assertTrue({'test_jump', 'test_look', 'test_facts', 'submit_game_task'} <= ids())
        self.assertIn('test_jump', m.moving_calls())
        self.assertNotIn('test_look', m.moving_calls())
        self.assertIn('test_facts', m.game_calls())
        self.assertIn('answer_game_task', m.one_call_tools())

    async def test_the_state_goes_to_the_talker_and_the_mind(self):
        await self.link()
        m = mind.Mind(Conversation(), body=self.env)
        ctx = ctx_with('今どんな感じ？')
        for built in (m.build(ctx, turn={}), m.build(ctx, talker_instructions='短い指示', turn={})):
            self.assertTrue(any('[テストの様子]' in (i.text_content or '') for i in built.items))

    async def test_moving_the_body_is_not_for_comments(self):
        with mock.patch.dict(tools.ENV_FROM_COMMENTS, self.env.from_comments()):
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
