"""Integration checks against an explicitly isolated, disposable PostgreSQL database."""
import asyncio
import os
import unittest
from unittest.mock import patch

import numpy as np

from speaker_store import Store, Relationship, SharedPersonError


@unittest.skipUnless(os.environ.get('CIEL_TEST_DB_URL'), 'isolated PostgreSQL not configured')
class SharedMemoryPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict(os.environ, {'CIEL_DB_URL': os.environ['CIEL_TEST_DB_URL'], 'CIEL_MEMORY_SCOPE': 'main'})
        self.env.start()
        self.addCleanup(self.env.stop)
        # Never run migration or writes against an application database.
        import psycopg
        probe = await psycopg.AsyncConnection.connect(os.environ['CIEL_TEST_DB_URL'], autocommit=True)
        database = (await (await probe.execute('SELECT current_database()')).fetchone())[0]
        await probe.close()
        if database != 'ciel_concurrency_test':
            self.fail('CIEL_TEST_DB_URL must point to ciel_concurrency_test')
        self.a, self.b = await asyncio.gather(Store.open(), Store.open())
        self.assertIsNotNone(self.a)
        self.assertIsNotNone(self.b)
        self.pid = await self.a.remember_person('Synthetic person', [np.ones(192)])
        self.extra: list[int] = []

    async def asyncTearDown(self):
        for pid in self.extra:
            await self.a.delete_person(pid)
        await self.a.delete_person(self.pid)
        await self.a.close()
        await self.b.close()

    async def test_two_sessions_cannot_overwrite_stale_notes(self):
        first, stale = await asyncio.gather(self.a.memory_snapshot(self.pid), self.b.memory_snapshot(self.pid))
        self.assertTrue(await self.a.apply_notes(self.pid, first, ['tea'], {}, []))
        self.assertFalse(await self.b.apply_notes(self.pid, stale, ['coffee'], {}, []))
        fresh = await self.b.memory_snapshot(self.pid)
        self.assertEqual([text for _, text in fresh['notes']], ['tea'])
        self.assertTrue(await self.b.apply_notes(self.pid, fresh, ['coffee'], {}, []))
        self.assertEqual([text for _, text in await self.a.notes(self.pid)], ['tea', 'coffee'])

    async def test_relationship_counts_survive_simultaneous_updates(self):
        first, stale = await asyncio.gather(self.a.memory_snapshot(self.pid), self.b.memory_snapshot(self.pid))
        self.assertTrue(await self.a.apply_relationship(self.pid, first, Relationship(sessions=1)))
        self.assertFalse(await self.b.apply_relationship(self.pid, stale, Relationship(sessions=1)))
        fresh = await self.b.memory_snapshot(self.pid)
        relation = fresh['relationship']
        relation.sessions += 1
        self.assertTrue(await self.b.apply_relationship(self.pid, fresh, relation))
        self.assertEqual((await self.a.relationship(self.pid)).sessions, 2)

    async def test_forget_invalidates_inflight_writers_and_remains_in_future_snapshots(self):
        old = await self.a.memory_snapshot(self.pid)
        await self.b.request_forget(self.pid, 'old preference')
        self.assertFalse(await self.a.apply_notes(self.pid, old, ['old preference'], {}, []))
        pending = await self.a.memory_snapshot(self.pid)
        self.assertTrue(pending['blocked'])
        self.assertFalse(await self.a.apply_relationship(self.pid, pending, Relationship(feeling='stale')))
        self.assertTrue(await self.a.apply_notes(self.pid, pending, [], {}, []))
        finished = await self.b.memory_snapshot(self.pid)
        self.assertFalse(finished['blocked'])
        self.assertEqual([f['request'] for f in finished['forgets']], ['old preference'])

    async def test_deleted_person_cannot_be_recreated_by_inflight_writer(self):
        old = await self.a.memory_snapshot(self.pid)
        await self.b.delete_person(self.pid)
        self.assertFalse(await self.a.apply_notes(self.pid, old, ['stale'], {}, []))
        self.assertIsNone(await self.a.memory_snapshot(self.pid))

    async def test_transaction_failure_does_not_rollback_another_tasks_rename(self):
        snapshot = await self.a.memory_snapshot(self.pid)
        entered, release = asyncio.Event(), asyncio.Event()
        real_change = self.a.change_notes

        async def fail(*args):
            await real_change(*args)
            entered.set()
            await release.wait()
            raise RuntimeError('synthetic rollback')

        with patch.object(self.a, 'change_notes', fail):
            writing = asyncio.create_task(self.a.apply_notes(self.pid, snapshot, ['rollback'], {}, []))
            await entered.wait()
            renaming = asyncio.create_task(self.a.rename(self.pid, 'Renamed'))
            await asyncio.sleep(0)
            self.assertFalse(renaming.done())
            release.set()
            with self.assertRaises(RuntimeError):
                await writing
            await renaming
        self.assertEqual(await self.a.notes(self.pid), [])
        self.assertEqual((await self.b.identity(self.pid))['name'], 'Renamed')

    async def test_device_owner_is_checked_by_secret_hash_and_removed_with_the_person(self):
        await self.a.pair_device('test-device-1', 'hash-a', self.pid)
        self.assertEqual(await self.b.device_owner('test-device-1', 'hash-a'), self.pid)
        self.assertIsNone(await self.b.device_owner('test-device-1', 'hash-b'))
        self.assertFalse(await self.b.unpair_device('test-device-1', 'hash-b'))
        self.assertTrue(await self.b.unpair_device('test-device-1', 'hash-a'))
        self.assertIsNone(await self.a.device_owner('test-device-1', 'hash-a'))
        other = await self.a.remember_person('Synthetic other', [np.ones(192)])
        await self.a.pair_device('test-device-2', 'hash-c', other)
        await self.a.delete_person(other)
        self.assertIsNone(await self.b.device_owner('test-device-2', 'hash-c'))

    async def test_voiceprints_of_one_channel_do_not_push_out_the_others(self):
        rng = np.random.default_rng(0)
        for _ in range(3):
            await self.a.add_voiceprints(self.pid, [rng.standard_normal(192) for _ in range(10)], 2.0, channel='device:x')
        rows = await (await self.a.conn.execute(
            'SELECT channel, count(*) FROM voiceprints WHERE person_id=%s GROUP BY channel ORDER BY channel NULLS FIRST',
            (self.pid,))).fetchall()
        self.assertEqual(rows, [(None, 1), ('device:x', 20)])

    async def test_dev_sees_only_shared_and_its_own_people(self):
        """本番（main）と開発用（dev）が同じ DB を使う（docs/services/shared-memory-ja.md）"""
        dev = Store(self.a.conn, 'dev')
        guest = await self.a.remember_person('Synthetic guest', [np.ones(192)])
        self.extra.append(guest)
        trial = await dev.remember_person('Synthetic trial', [np.ones(192)])
        self.extra.append(trial)
        main_ids = {row[0] for row in await self.a.load_all()}
        self.assertTrue({self.pid, guest} <= main_ids)
        self.assertNotIn(trial, main_ids)
        self.assertNotIn(trial, await self.a.versions())
        seen = {row[0] for row in await dev.load_all()}
        self.assertIn(trial, seen)
        self.assertNotIn(self.pid, seen)
        await self.a.conn.execute('UPDATE people SET shared = true WHERE id = %s', (self.pid,))
        seen = {row[0] for row in await dev.load_all()}
        self.assertIn(self.pid, seen)
        self.assertNotIn(guest, seen)
        self.assertIn(self.pid, await dev.versions())

    async def test_dev_writes_reach_main_but_cannot_delete_the_shared_person(self):
        dev = Store(self.a.conn, 'dev')
        await self.a.conn.execute('UPDATE people SET shared = true WHERE id = %s', (self.pid,))
        snapshot = await dev.memory_snapshot(self.pid)
        self.assertTrue(await dev.apply_notes(self.pid, snapshot, ['tea'], {}, []))
        self.assertEqual([t for _, t in await self.a.notes(self.pid)], ['tea'])
        origin = await (await self.a.conn.execute(
            'SELECT origin FROM person_notes WHERE person_id = %s', (self.pid,))).fetchone()
        self.assertEqual(origin[0], 'dev')
        self.assertTrue(await dev.request_forget(self.pid, 'tea'))
        self.assertTrue((await self.a.memory_snapshot(self.pid))['blocked'])
        with self.assertRaises(SharedPersonError):
            await dev.delete_person(self.pid)
        with self.assertRaises(SharedPersonError):
            await dev.rename(self.pid, 'Renamed')
        await self.a.pair_device('test-device-3', 'hash-d', self.pid)
        self.assertEqual(await dev.device_owner('test-device-3', 'hash-d'), self.pid)
        self.assertFalse(await dev.unpair_device('test-device-3', 'hash-d'))
        self.assertIsNotNone(await self.a.identity(self.pid))


@unittest.skipUnless(os.environ.get('CIEL_TEST_DB_URL'), 'isolated PostgreSQL not configured')
class RecallPostgresTests(unittest.IsolatedAsyncioTestCase):
    """Associative recall tables (memories / note_index) on a disposable database."""
    MODEL = 'test-embedder'

    async def asyncSetUp(self):
        self.env = patch.dict(os.environ, {'CIEL_DB_URL': os.environ['CIEL_TEST_DB_URL'], 'CIEL_MEMORY_SCOPE': 'main'})
        self.env.start()
        self.addCleanup(self.env.stop)
        import psycopg
        probe = await psycopg.AsyncConnection.connect(os.environ['CIEL_TEST_DB_URL'], autocommit=True)
        database = (await (await probe.execute('SELECT current_database()')).fetchone())[0]
        await probe.close()
        if database != 'ciel_concurrency_test':
            self.fail('CIEL_TEST_DB_URL must point to ciel_concurrency_test')
        self.store = await Store.open()
        self.assertIsNotNone(self.store)
        await self.store.conn.execute('DELETE FROM memories')
        await self.store.conn.execute('DELETE FROM ciel_events')
        self.pid = await self.store.remember_person('Synthetic recall person', [np.ones(192)])

    async def asyncTearDown(self):
        await self.store.conn.execute('DELETE FROM memories')
        await self.store.conn.execute('DELETE FROM ciel_events')
        await self.store.delete_person(self.pid)
        await self.store.close()

    async def add_note(self, text):
        snapshot = await self.store.memory_snapshot(self.pid)
        self.assertTrue(await self.store.apply_notes(self.pid, snapshot, [text], {}, []))
        return next(i for i, t in await self.store.notes(self.pid) if t == text)

    async def test_events_stay_in_memories_after_the_diary_drops_them(self):
        for i in range(3):
            await self.store.add_ciel_event('minecraft', f'event {i}', keep=1)
        self.assertEqual(len(await self.store.ciel_events(10)), 1)
        got = await self.store.recall_candidates(self.MODEL, None, None)
        self.assertEqual(sorted(c.text for c in got), ['event 0', 'event 1', 'event 2'])

    async def test_places_are_scoped_to_their_world_and_invalidated_not_deleted(self):
        await self.store.add_ciel_event('minecraft', 'base A', 10, memory_kind='game_place', world='mc:w1',
                                        ref='mc:w1/base/1,2,3', importance=4)
        await self.store.add_ciel_event('minecraft', 'base B', 10, memory_kind='game_place', world='mc:w2',
                                        ref='mc:w2/base/1,2,3', importance=4)
        self.assertEqual(await self.store.invalidate_memories('mc:w1/base/1,2,3'), 1)
        self.assertEqual(await self.store.invalidate_memories('mc:w1/base/1,2,3'), 0)
        got = {c.text: c for c in await self.store.recall_candidates(self.MODEL, 'mc:w1', None)}
        self.assertEqual(set(got), {'base A'})
        self.assertIsNotNone(got['base A'].invalidated_at)
        self.assertEqual(got['base A'].importance, 4)
        other = await self.store.recall_candidates(self.MODEL, 'mc:w2', None)
        self.assertIsNone(other[0].invalidated_at)

    async def test_index_is_written_and_redone_when_the_note_changes(self):
        await self.store.add_ciel_event('minecraft', 'built a house', 10)
        nid = await self.add_note('likes curry')
        note_id = f'note:{nid}'
        todo = {r['id']: r for r in await self.store.unindexed(self.MODEL, True, 10)}
        self.assertIn(note_id, todo)
        mem_id = next(i for i in todo if i.startswith('mem:'))
        vec = np.array([1, 0, 0, 0], dtype=np.float32)
        await self.store.set_index(mem_id, 'built a house', 'home, rest', vec, self.MODEL, 'built a house\nhome, rest')
        await self.store.set_index(note_id, 'likes curry', 'food', vec, self.MODEL, 'likes curry\nfood')
        self.assertEqual(await self.store.unindexed(self.MODEL, True, 10), [])
        got = {c.id: c for c in await self.store.recall_candidates(self.MODEL, None, self.pid)}
        self.assertEqual(got[mem_id].keys, 'home, rest')
        self.assertEqual(got[note_id].keys, 'food')
        np.testing.assert_allclose(got[note_id].embedding, vec)
        # Another embedding model: vectors are not mixed and the work is listed again.
        other = {c.id: c for c in await self.store.recall_candidates('other-model', None, self.pid)}
        self.assertIsNone(other[note_id].embedding)
        self.assertEqual(len(await self.store.unindexed('other-model', True, 10)), 2)
        # The note is rewritten: its old keys and vector are not used, and it is indexed again.
        snapshot = await self.store.memory_snapshot(self.pid)
        self.assertTrue(await self.store.apply_notes(self.pid, snapshot, [], {nid: 'likes mild curry'}, []))
        got = {c.id: c for c in await self.store.recall_candidates(self.MODEL, None, self.pid)}
        self.assertEqual(got[note_id].keys, '')
        self.assertIsNone(got[note_id].embedding)
        self.assertEqual([r['id'] for r in await self.store.unindexed(self.MODEL, True, 10)], [note_id])

    async def test_notes_only_for_the_given_person_and_recall_is_counted(self):
        await self.add_note('private note')
        self.assertFalse([c for c in await self.store.recall_candidates(self.MODEL, None, None) if c.kind == 'note'])
        await self.store.add_ciel_event('minecraft', 'saw a village', 10)
        mem = (await self.store.recall_candidates(self.MODEL, None, None))[0]
        await self.store.mark_recalled([mem.id, 'note:1'])
        row = await (await self.store.conn.execute(
            'SELECT recall_count, last_recalled_at IS NOT NULL FROM memories WHERE id = %s',
            (int(mem.id.split(':')[1]),))).fetchone()
        self.assertEqual(tuple(row), (1, True))

    async def test_notes_without_consent_are_not_indexed(self):
        await self.add_note('note')
        await self.store.conn.execute('UPDATE people SET notes_consented_at = NULL WHERE id = %s', (self.pid,))
        self.assertEqual([r for r in await self.store.unindexed(self.MODEL, True, 10) if r['id'].startswith('note:')], [])
