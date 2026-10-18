"""Integration checks against an explicitly isolated, disposable PostgreSQL database."""
import asyncio
import os
import unittest
from unittest.mock import patch

import numpy as np

from speaker_store import Store, Relationship


@unittest.skipUnless(os.environ.get('CIEL_TEST_DB_URL'), 'isolated PostgreSQL not configured')
class SharedMemoryPostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict(os.environ, {'CIEL_DB_URL': os.environ['CIEL_TEST_DB_URL']})
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

    async def asyncTearDown(self):
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
