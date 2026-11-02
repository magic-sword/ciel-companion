"""Ciel's likes grow from what really happened: slowly, with evidence from more than one day, and traceably."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

import growth

NOW = datetime(2026, 11, 3, 6, 0, tzinfo=timezone.utc)
EVENTS = [(3, NOW - timedelta(hours=1), 'song', '歌を最後まで聴かせてもらった（2:10）'),
          (2, NOW - timedelta(days=2), 'song', '歌を最後まで聴かせてもらった（3:05）'),
          (1, NOW - timedelta(days=2, hours=1), 'touch', '頭をなでてもらった')]
LIKES = [(10, 'like', 'ゆっくりした歌', '歌を聴かせてもらって', [])]


def change(**kw):
    return {'action': 'add', 'kind': 'like', 'text': 'なでてもらうこと', 'why': 'うれしかった', 'evidence': [1, 3], **kw}


class CheckTests(unittest.TestCase):
    def test_needs_evidence_from_more_than_one_day(self):
        self.assertIsNone(growth.check(change(evidence=[1, 3]), LIKES, EVENTS))
        self.assertEqual(growth.check(change(evidence=[1, 2]), LIKES, EVENTS), 'too_little_evidence')   # same day
        self.assertEqual(growth.check(change(evidence=[3]), LIKES, EVENTS), 'too_little_evidence')
        self.assertEqual(growth.check(change(evidence=[3, 99]), LIKES, EVENTS), 'unknown_evidence')

    def test_kind_text_and_duplicates(self):
        self.assertEqual(growth.check(change(kind='love'), LIKES, EVENTS), 'kind')
        self.assertEqual(growth.check(change(text=' '), LIKES, EVENTS), 'text')
        self.assertEqual(growth.check(change(text='ゆっくりした歌'), LIKES, EVENTS), 'duplicate')
        self.assertIsNone(growth.check(change(kind='dislike', text='強くつつかれること'), LIKES, EVENTS))

    def test_cap_and_existing_likes(self):
        many = [(i, 'like', f'好み{i}', '', []) for i in range(growth.MAX_LIKES)]
        self.assertEqual(growth.check(change(), many, EVENTS), 'too_many')
        self.assertEqual(growth.check(change(action='remove', id=99, evidence=[3]), LIKES, EVENTS), 'unknown_like')
        self.assertEqual(growth.check(change(action='remove', id=10, evidence=[]), LIKES, EVENTS), 'too_little_evidence')
        self.assertIsNone(growth.check(change(action='remove', id=10, evidence=[3]), LIKES, EVENTS))

    def test_context_for_the_conversation(self):
        self.assertEqual(growth.context([]), '')
        text = growth.context(LIKES)
        self.assertIn('好きになってきた：ゆっくりした歌（歌を聴かせてもらって）', text)


def grower(reply, *, added=1, last=None):
    store = SimpleNamespace(last_like_change=AsyncMock(return_value=last), ciel_likes=AsyncMock(return_value=LIKES),
                            ciel_events=AsyncMock(return_value=EVENTS), change_ciel_like=AsyncMock(return_value=11))
    content = json.dumps({'change': reply}, ensure_ascii=False)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=None)))))
    return growth.Grower(store, SimpleNamespace(added=added), 'CORE', 'GROW', client=client), store, client


class FlushTests(unittest.IsolatedAsyncioTestCase):
    async def test_applies_a_checked_change_with_copied_evidence(self):
        g, store, client = grower(change())
        self.assertEqual(await g.flush(NOW), 'add')
        request = json.loads(client.chat.completions.create.await_args.kwargs['messages'][1]['content'])
        self.assertEqual([e['id'] for e in request['events']], [3, 2, 1])
        action, like_id, kind, text, why, evidence = store.change_ciel_like.await_args.args
        self.assertEqual((action, kind, text), ('add', 'like', 'なでてもらうこと'))
        self.assertEqual([e['text'] for e in evidence], ['歌を最後まで聴かせてもらった（2:10）', '頭をなでてもらった'])

    async def test_does_not_look_without_new_events_or_too_soon(self):
        g, store, client = grower(change(), added=0)
        self.assertEqual(await g.flush(NOW), 'skip')
        g, store, client = grower(change(), last=NOW - timedelta(hours=2))
        self.assertEqual(await g.flush(NOW), 'too_soon')
        client.chat.completions.create.assert_not_awaited()

    async def test_none_and_rejected_changes_write_nothing(self):
        g, store, _ = grower({'action': 'none'})
        self.assertEqual(await g.flush(NOW), 'none')
        g, store, _ = grower(change(evidence=[3]))
        self.assertEqual(await g.flush(NOW), 'rejected:too_little_evidence')
        store.change_ciel_like.assert_not_awaited()

    async def test_remove_keeps_the_old_text_for_the_record(self):
        g, store, _ = grower({'action': 'remove', 'id': 10, 'evidence': [3]})
        self.assertEqual(await g.flush(NOW), 'remove')
        self.assertEqual(store.change_ciel_like.await_args.args[:4], ('remove', 10, 'like', 'ゆっくりした歌'))

    async def test_without_a_db_it_does_not_grow(self):
        g = growth.Grower(None, SimpleNamespace(added=3), 'CORE', 'GROW')
        self.assertEqual(await g.flush(NOW), 'skip')


if __name__ == '__main__':
    unittest.main()
