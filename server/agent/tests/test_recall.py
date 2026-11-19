"""関連性で思い出す（recall.py）：公開範囲、関連度・新しさ・重要度の順位、補足の形、索引づくり、ゲームの場所の記憶。"""
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

import numpy as np

import diary
import game_env
from jst import JST
import recall
from recall import Candidate, Situation

NOW = datetime(2026, 11, 20, 21, 0, tzinfo=JST)
HEADER = '[思い出したこと]（シエルの記憶）'


def c(id, kind='diary', text='', days=1, **kw):
    return Candidate(id=id, kind=kind, text=text, at=NOW - timedelta(days=days), **kw)


class Words(recall.Embedder):
    """決まった語を含むかで向きを決める、テスト用の埋め込み"""
    name = 'words'
    AXES = ['休', '歌', '料理']

    def embed(self, texts, *, query):
        out = []
        for t in texts:
            v = np.array([1.0 if a in t else 0.0 for a in self.AXES] + [0.05], dtype=np.float32)
            out.append(v / np.linalg.norm(v))
        return np.stack(out)


class EligibleTest(unittest.TestCase):
    def test_notes_only_for_the_identified_person_in_private(self):
        note = c('note:1', 'note', '辛いものが苦手', person_id=2)
        self.assertTrue(recall.eligible(note, Situation('solo', 2)))
        self.assertTrue(recall.eligible(note, Situation('close', 2)))
        self.assertFalse(recall.eligible(note, Situation('public', 2)))
        self.assertFalse(recall.eligible(note, Situation('solo', 3)))
        self.assertFalse(recall.eligible(note, Situation('solo', None)))

    def test_game_memories_belong_to_their_world(self):
        place = c('mem:1', 'game_place', '拠点を決めた', world='minecraft:w1')
        self.assertTrue(recall.eligible(place, Situation(world='minecraft:w1')))
        self.assertFalse(recall.eligible(place, Situation(world='minecraft:w0')))
        self.assertFalse(recall.eligible(place, Situation(world=None)))
        self.assertTrue(recall.eligible(c('mem:2', 'game_place', '拠点'), Situation(world=None)))   # ワールド不明の古い記憶
        self.assertTrue(recall.eligible(c('mem:3', 'diary', '歌を聴いた'), Situation('public')))


class RankTest(unittest.TestCase):
    def test_keys_connect_words_that_do_not_overlap(self):
        base = c('mem:1', 'game_place', '森の横に拠点を決めた', keys='休む、寝る、夜を越す', days=3)
        other = c('mem:2', 'diary', '花を摘んだ', days=1)
        got = recall.rank([base, other], Situation(), 'ちょっと疲れたね。どこかで休もうか', None, NOW)
        self.assertEqual([r.id for r in got], ['mem:1'])
        self.assertGreater(got[0].details['lexical'], 0)
        self.assertEqual(recall.rank([c('mem:1', text='森の横に拠点を決めた')], Situation(), 'どこかで休もうか', None, NOW), [])

    def test_embedding_relevance_and_unrelated_talk(self):
        e = Words()
        rest = c('mem:1', text='拠点で休んだ', embedding=e.embed(['拠点で休んだ'], query=False)[0])
        song = c('mem:2', text='歌を聴いた', embedding=e.embed(['歌を聴いた'], query=False)[0])
        got = recall.rank([rest, song], Situation(), 'どこで休む？', e.embed(['どこで休む？'], query=True)[0], NOW)
        self.assertEqual(got[0].id, 'mem:1')
        self.assertEqual(recall.rank([rest, song], Situation(), '今日は寒いね', e.embed(['今日は寒いね'], query=True)[0], NOW), [])

    def test_recent_and_important_rank_higher_but_old_stays_reachable(self):
        old = c('mem:1', text='ゾンビを倒した', days=200)
        new = c('mem:2', text='ゾンビを倒した', days=1)
        big = c('mem:3', text='ゾンビを倒した', days=1, importance=5)
        got = recall.rank([old, new, big], Situation(), 'ゾンビを倒した', None, NOW)
        self.assertEqual([r.id for r in got], ['mem:3', 'mem:2', 'mem:1'])
        self.assertGreaterEqual(recall.recency(NOW - timedelta(days=1000), NOW), recall.RECENCY_FLOOR)

    def test_invalidated_place_is_marked_past(self):
        gone = c('mem:1', 'game_place', '森の横に拠点を決めた', keys='休む', invalidated_at=NOW - timedelta(days=1))
        got = recall.rank([gone], Situation(), 'どこで休む', None, NOW)
        self.assertTrue(got[0].past)
        text = recall.context(got, NOW, HEADER)
        self.assertIn('森の横に拠点を決めた。でも、その場所は今はもう無い', text)

    def test_time_words_pick_that_day(self):
        y = recall.time_window('きのう何したっけ？', NOW)
        self.assertEqual((y[0].day, y[1].day), (19, 20))
        self.assertEqual(recall.time_window('3日前のこと', NOW)[0].day, 17)
        self.assertEqual(recall.time_window('三日前のこと', NOW)[0].day, 17)
        self.assertIsNone(recall.time_window('前にゾンビを倒した', NOW))
        pat = c('mem:1', text='頭をなでてもらった', days=1)
        old = c('mem:2', text='花を摘んだ', days=3)
        self.assertEqual([r.id for r in recall.rank([pat, old], Situation(), 'きのう何したっけ？', None, NOW)], ['mem:1'])

    def test_context_reads_as_a_dated_list(self):
        items = recall.rank([c('mem:1', text='歌を聴かせてもらった', days=1)], Situation(), '歌を聴いて', None, NOW)
        self.assertEqual(recall.context(items, NOW, HEADER), HEADER + '\n- きのう：歌を聴かせてもらった')
        self.assertEqual(recall.context([], NOW, HEADER), '')


class FakeStore:
    def __init__(self, candidates=(), rows=()):
        self.candidates = list(candidates)
        self.rows = list(rows)
        self.recalled, self.indexed, self.asked = [], [], []

    async def recall_candidates(self, model, world, person_id):
        self.asked.append((model, world, person_id))
        return self.candidates

    async def mark_recalled(self, ids):
        self.recalled.append(ids)

    async def unindexed(self, model, want_keys, limit):
        done = {i for i, *_ in self.indexed}
        return [r for r in self.rows if r['id'] not in done][:limit]

    async def set_index(self, id, text, keys, embedding, model, doc):
        self.indexed.append((id, text, keys, embedding, model, doc))


class RecallTest(unittest.IsolatedAsyncioTestCase):
    async def test_notes_are_asked_only_in_private(self):
        store = FakeStore([c('mem:1', text='歌を聴いた')])
        r = recall.Recall(store, None, clock=lambda: NOW)
        await r.for_turn('歌を聴いて', Situation('public', 2, 'w'))
        await r.for_turn('歌を聴いて', Situation('solo', 2, 'w'))
        self.assertEqual(store.asked, [('', 'w', None), ('', 'w', 2)])
        self.assertEqual(store.recalled, [['mem:1'], ['mem:1']])

    async def test_the_same_memory_steps_back_for_a_while(self):
        t = [0.0]
        a = c('mem:1', text='歌を聴いた', days=1)
        b = c('mem:2', text='歌を聴いたあと、また歌った', days=30)
        r = recall.Recall(FakeStore([a, b]), None, clock=lambda: NOW, monotonic=lambda: t[0])
        recall.TOP_K, k = 1, recall.TOP_K
        try:
            first = await r.for_turn('歌を聴いた', Situation())
            second = await r.for_turn('歌を聴いた', Situation())
            t[0] = recall.Recall.REPEAT_SECONDS + 1
            third = await r.for_turn('歌を聴いた', Situation())
        finally:
            recall.TOP_K = k
        self.assertEqual([first[0].id, second[0].id, third[0].id], ['mem:1', 'mem:2', 'mem:1'])

    async def test_empty_query_or_no_store(self):
        self.assertEqual(await recall.Recall(FakeStore(), None).for_turn('  ', Situation()), [])
        self.assertEqual(await recall.Recall(None, None).for_turn('歌', Situation()), [])


class IndexerTest(unittest.IsolatedAsyncioTestCase):
    async def test_keys_then_embedding_of_text_and_keys(self):
        store = FakeStore(rows=[{'id': 'mem:1', 'text': '拠点を決めた', 'keys': None},
                                {'id': 'note:4', 'text': '辛いものが苦手', 'keys': 'カレー'}])
        keys = SimpleNamespace(write=AsyncMock(return_value={'mem:1': '休む、寝る'}))
        ix = recall.Indexer(store, Words(), keys)
        self.assertFalse(await ix.step())
        keys.write.assert_awaited_once_with([('mem:1', '拠点を決めた')])
        got = {i: (k, doc, model) for i, _, k, _, model, doc in store.indexed}
        self.assertEqual(got['mem:1'], ('休む、寝る', '拠点を決めた\n休む、寝る', 'words'))
        self.assertEqual(got['note:4'], ('カレー', '辛いものが苦手\nカレー', 'words'))

    async def test_a_failed_key_waits_instead_of_embedding_text_alone(self):
        store = FakeStore(rows=[{'id': 'mem:1', 'text': '拠点を決めた', 'keys': None}])
        keys = SimpleNamespace(write=AsyncMock(side_effect=RuntimeError('down')))
        self.assertFalse(await recall.Indexer(store, Words(), keys).step())
        self.assertEqual(store.indexed, [])

    async def test_without_key_writer_or_embedder(self):
        store = FakeStore(rows=[{'id': 'mem:1', 'text': '拠点を決めた', 'keys': None}])
        self.assertFalse(await recall.Indexer(store, None, None).step())
        self.assertEqual(store.indexed, [('mem:1', '拠点を決めた', '', None, '', '拠点を決めた')])


class KeyWriterTest(unittest.IsolatedAsyncioTestCase):
    async def test_only_asked_ids_and_bounded_text(self):
        reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content='{"keys": {"mem:1": "休む、 寝る", "mem:9": "余計", "mem:2": 3}}'))], usage=None)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=reply))))
        got = await recall.KeyWriter('指示', client).write([('mem:1', '拠点'), ('mem:2', '歌')])
        self.assertEqual(got, {'mem:1': '休む、 寝る'})


class GameMemoryTest(unittest.IsolatedAsyncioTestCase):
    def env(self):
        env = game_env.GameEnv('minecraft', 'http://unused', connect=lambda e: None)
        env.linked, env.state = True, {'world': 'w1'}
        env.diary = SimpleNamespace(added=[], lost=[])
        env.diary.add = lambda kind, text, **kw: env.diary.added.append((kind, text, kw))
        env.diary.invalidate = env.diary.lost.append
        return env

    def test_places_keep_world_and_reference(self):
        env = self.env()
        self.assertEqual(env.world, 'minecraft:w1')
        env._remember({'kind': 'place_lost', 'ref': 'base/0,70,0'})
        env._remember({'kind': 'game_place', 'ref': 'base/1,2,3', 'importance': 4, 'text': 'マイクラで拠点を決めた'})
        env._remember('マイクラで zombie を倒した')
        self.assertEqual(env.diary.lost, ['minecraft:w1/base/0,70,0'])
        self.assertEqual(env.diary.added, [
            ('minecraft', 'マイクラで拠点を決めた',
             {'memory_kind': 'game_place', 'world': 'minecraft:w1', 'ref': 'minecraft:w1/base/1,2,3', 'importance': 4}),
            ('minecraft', 'マイクラで zombie を倒した', {})])

    def test_a_base_set_again_elsewhere_is_a_new_memory(self):
        env = self.env()
        place = {'kind': 'game_place', 'importance': 4, 'text': 'マイクラで拠点を決めた'}
        env._remember({**place, 'ref': 'base/1,2,3'})
        env._remember({**place, 'ref': 'base/1,2,3'})
        env._remember({'kind': 'place_lost', 'ref': 'base/1,2,3'})
        env._remember({**place, 'ref': 'base/9,9,9'})
        self.assertEqual([a[2]['ref'] for a in env.diary.added],
                         ['minecraft:w1/base/1,2,3', 'minecraft:w1/base/9,9,9'])

    def test_without_world_no_reference_is_made(self):
        env = self.env()
        env.state = {}
        env._remember({'kind': 'game_place', 'ref': 'base/1,2,3', 'text': '拠点'})
        env._remember({'kind': 'place_lost', 'ref': 'base/1,2,3'})
        self.assertIsNone(env.world)
        self.assertEqual(env.diary.added[0][2]['ref'], None)
        self.assertEqual(env.diary.lost, [])


class DiaryMemoryTest(unittest.IsolatedAsyncioTestCase):
    async def test_place_memories_reach_the_store(self):
        store = SimpleNamespace(add_ciel_event=AsyncMock(), invalidate_memories=AsyncMock(return_value=1))
        d = diary.Diary(store)
        d.add('minecraft', '拠点を決めた', memory_kind='game_place', world='minecraft:w1', ref='minecraft:w1/base/1', importance=4)
        d.invalidate('minecraft:w1/base/0')
        await d.drain()
        store.add_ciel_event.assert_awaited_once_with('minecraft', '拠点を決めた', diary.KEEP, memory_kind='game_place',
                                                      world='minecraft:w1', ref='minecraft:w1/base/1', importance=4)
        store.invalidate_memories.assert_awaited_once_with('minecraft:w1/base/0')


class SpeakerTest(unittest.TestCase):
    def test_recall_person_needs_sure_consented_unsuppressed(self):
        import speakers
        book = speakers.SpeakerBook(None)
        k = SimpleNamespace(person_id=2, notes_ok=True)
        book.known = [k]
        sp = SimpleNamespace(person_id=2, memory_suppressed=False)
        book.last, book.last_sure = sp, True
        self.assertEqual(book.recall_person(), 2)
        book.last_sure = False
        self.assertIsNone(book.recall_person())
        book.last_sure, sp.memory_suppressed = True, True
        self.assertIsNone(book.recall_person())
        sp.memory_suppressed, k.notes_ok = False, False
        self.assertIsNone(book.recall_person())


if __name__ == '__main__':
    unittest.main()
