"""遊んでいるあいだの振り分けの 2 段目（router.py）と、例文の育ち方・約束の受け皿（mind.py の after_reply）"""
import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np

import router
from tools.goals import GOAL_TOOLS

KEYS = ('渡', '欲し', 'ちょうだい', '作', '集め', 'えらい', 'こんばん', '見え', 'どこ')


class FakeEmbeddings:
    """文に含まれる言葉で決まるベクトル（言葉が重なるほど近い）"""

    def __init__(self):
        self.calls = 0

    async def create(self, model, input, dimensions):
        self.calls += 1
        out = []
        for text in input:
            v = [1.0 if k in text else 0.0 for k in KEYS] + [0.0] * (dimensions - len(KEYS))
            v[-1] = 0.2   # 何も含まない文どうしが同じ向きにならないように
            out.append(SimpleNamespace(embedding=v))
        return SimpleNamespace(data=out)


class FakeStore:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.added, self.removed = [], []

    async def route_examples(self, game):
        return self.rows

    async def add_route_example(self, game, tool, text, embedding, source, keep):
        self.added.append((tool, text, source))

    async def remove_route_example(self, game, text):
        self.removed.append(text)


def make(store=None, seeds=None):
    r = router.Router('test', store=store, client=SimpleNamespace(embeddings=FakeEmbeddings()))
    seeds = seeds or [('それちょうだい', 'give_item'), ('剣を作って', 'craft_item'), ('えらいね', None), ('こんばんは', None)]
    router.seeds = lambda game, _s=seeds: list(_s)
    return r


class SeedsTest(unittest.TestCase):
    # 道具ごとのきっかけはゲームの側が持つ（server/minecraft の src/ciel/routes.json。書き忘れは test/ciel.test.js が確かめる）

    def test_seeds_given_by_the_game_are_used(self):
        r = router.Router('test', client=None, seeds=[('跳んで', 'test_jump'), ('えらいね', None)])
        self.assertEqual(r._seeds, [('跳んで', 'test_jump'), ('えらいね', None)])

    def test_the_name_and_marks_are_dropped_before_comparing(self):
        self.assertEqual(router.norm('シエル、どこにいる？'), 'どこにいる')
        self.assertEqual(router.norm('シエル'), 'シエル')   # 名前だけなら、そのまま


class RouterTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._seeds = router.seeds

    def tearDown(self):
        router.seeds = self._seeds

    async def test_a_new_way_of_asking_goes_to_the_nearest_tool(self):
        r = make()
        self.assertEqual(await r.wants_mind('それ渡してちょうだい'), 'give_item')
        self.assertIsNone(await r.wants_mind('えらいね、ほんとに'))

    async def test_learned_examples_from_the_db_are_used(self):
        v = np.zeros(router.DIMS, dtype=np.float32)
        v[KEYS.index('欲し')] = 1.0
        r = make(store=FakeStore([('二本目が欲しいな', 'give_item', v)]))
        self.assertIsNone(await make().wants_mind('欲しいな'))       # 最初の例文だけでは遠い
        self.assertEqual(await r.wants_mind('欲しいな'), 'give_item')   # 育った例文で届く

    async def test_learning_skips_the_same_and_replaces_the_opposite(self):
        store = FakeStore()
        r = make(store=store)
        self.assertEqual(await r.learn('二本目が欲しいな', 'give_item', 'promise'), 'added')
        self.assertEqual(await r.learn('欲しいなあ、それが', 'give_item', 'tool'), 'same')
        self.assertEqual(await r.learn('欲しいって話をしてた', None, 'no_tool'), 'replaced')   # 新しいほうを信じる
        self.assertEqual(store.added, [('give_item', '二本目が欲しいな', 'promise'), (None, '欲しいって話をしてた', 'no_tool')])
        self.assertEqual(store.removed, ['二本目が欲しいな'])
        self.assertIsNone(await r.wants_mind('欲しい'))

    async def test_a_slow_or_broken_embedding_keeps_the_talker(self):
        r = make()

        async def broken(**kw):
            raise RuntimeError('down')
        r._client = SimpleNamespace(embeddings=SimpleNamespace(create=broken))
        self.assertIsNone(await r.wants_mind('それちょうだい'))


class FakeBody:
    """ゲームの環境（game_env.GameEnv）のうち、心が見るところ。道具の役目はゲームの決まりから"""
    ROLES = {'act': {'give_item', 'craft_item'}, 'look': {'look_around'}, 'know': set()}

    def __init__(self):
        self.linked, self.in_world, self.route_words = True, True, None

    def playing(self):
        return self.linked and self.in_world

    def tool_ids(self, *roles):
        return frozenset(n for r in roles for n in self.ROLES.get(r, ()))


class AfterReplyTest(unittest.IsolatedAsyncioTestCase):
    def make_mind(self):
        import mind
        m = mind.Mind(None)
        m.body = FakeBody()
        m.router = SimpleNamespace(learn=Mock(side_effect=lambda *a: asyncio.sleep(0)))
        m.on_promise = Mock()
        return m

    def ctx(self, text):
        from livekit.agents import llm
        c = llm.ChatContext()
        c.add_message(role='user', content=text)
        return c

    async def test_a_tool_call_teaches_that_tool(self):
        m = self.make_mind()
        m.after_reply(self.ctx('シエル、それくれる？'), 'mind', '', ['give_item'], True)
        m.router.learn.assert_called_once_with('シエル、それくれる？', 'give_item', 'tool')

    async def test_a_talker_promise_hands_over_to_the_mind_and_teaches_the_miss(self):
        m = self.make_mind()
        said = 'うん、シエルが持ってる二本目が欲しいな。'
        m.after_reply(self.ctx(said), 'talker', '[happy]もちろんです。二本目の石のつるはし、すぐに渡しますね。', [], True)
        m.on_promise.assert_called_once()
        m.router.learn.assert_not_called()
        m.after_reply(self.ctx(said), 'mind', '渡したのです', ['give_item'], True)   # 心が約束を道具でやった
        m.router.learn.assert_called_once_with(said, 'give_item', 'promise')

    async def test_too_much_semantic_routing_teaches_the_talker_only_for_moving_tools(self):
        m = self.make_mind()
        m.last_why, m.semantic_tool = 'semantic', 'look_around'
        m.after_reply(self.ctx('どこにいるの'), 'mind', '湖のそばなのです', [], True)
        m.router.learn.assert_not_called()   # 見る頼みは、様子から道具なしで答えることもある
        m.last_why, m.semantic_tool = 'semantic', 'craft_item'
        m.after_reply(self.ctx('作り方の話をしてたんだ'), 'mind', 'そうなのですね', [], True)
        m.router.learn.assert_called_once_with('作り方の話をしてたんだ', None, 'no_tool')

    async def test_not_playing_learns_nothing(self):
        m = self.make_mind()
        m.body.in_world = False
        m.after_reply(self.ctx('それくれる？'), 'mind', '', ['give_item'], True)
        m.router.learn.assert_not_called()

    def test_promises_are_her_words_for_moving(self):
        import mind
        for text in ('すぐに渡しますね', 'はい、ついていきます！', '原木を集めておきます', '作りますね'):
            self.assertRegex(text, mind.PROMISE)
        for text in ('うれしいのです', 'そう思っています', 'いい感じなら安心しました', '作り方を教えます'):
            self.assertNotRegex(text, mind.PROMISE)


class LearnLengthTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._seeds = router.seeds

    def tearDown(self):
        router.seeds = self._seeds

    async def test_short_replies_and_long_talks_are_not_learned(self):
        # 「うん、お願い」が渡すきっかけになった件（2026-11-07）：流れしだいの短い返事と、話がまざる長い発言は育てない
        r = make(store=FakeStore())
        self.assertEqual(await r.learn('うん、お願い。', 'give_item', 'promise'), 'skip')
        self.assertEqual(await r.learn('私じゃなくて 作ってほしいな 今私、ツルハシをシエルに返したから、それで石を掘って',
                                       'craft_item', 'tool'), 'skip')
        self.assertEqual(await r.learn('石のピッケルが欲しいな', 'give_item', 'tool'), 'added')
