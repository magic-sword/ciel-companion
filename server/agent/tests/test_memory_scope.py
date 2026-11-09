"""本番（main）と開発用（dev）が同じ DB を使うときの、見える人と直せる人の決まり（docs/services/shared-memory-ja.md）。DB は使わない。"""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import numpy as np

import speaker_store
from speaker_store import SharedPersonError, Store, memory_scope, visible
from speakers import SessionSpeaker, SpeakerBook


class FakeConn:
    """execute の SQL を覚え、決めた行を返す"""

    def __init__(self, rows: dict[str, list]):
        self.rows = rows      # SQL の一部 → 返す行
        self.sql: list[tuple[str, tuple]] = []

    async def execute(self, sql, params=()):
        self.sql.append((sql, params))
        rows = next((r for key, r in self.rows.items() if key in sql), [])
        return SimpleNamespace(fetchone=AsyncMock(return_value=rows[0] if rows else None),
                               fetchall=AsyncMock(return_value=rows), rowcount=len(rows))

    def ran(self, word: str) -> bool:
        return any(word in sql for sql, _ in self.sql)


class ScopeTests(unittest.TestCase):
    def test_default_is_main_and_unknown_scope_is_rejected(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(memory_scope(), 'main')
        with patch.dict(os.environ, {'CIEL_MEMORY_SCOPE': 'dev'}):
            self.assertEqual(memory_scope(), 'dev')
        with patch.dict(os.environ, {'CIEL_MEMORY_SCOPE': 'prod'}):
            with self.assertRaises(ValueError):
                memory_scope()

    def test_main_sees_only_main_people_and_dev_sees_dev_and_shared(self):
        self.assertEqual(visible('main'), "p.origin = 'main'")
        self.assertIn("p.origin = 'dev'", visible('dev'))
        self.assertIn("p.origin = 'main' AND p.shared", visible('dev'))


class StoreScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_people_and_versions_are_filtered_by_scope(self):
        for scope in ('main', 'dev'):
            conn = FakeConn({})
            store = Store(conn, scope)
            await store.load_all()
            await store.versions()
            self.assertTrue(all(visible(scope) in sql for sql, _ in conn.sql))

    async def test_new_people_and_notes_carry_the_scope(self):
        conn = FakeConn({'RETURNING id': [(5,)]})
        store = Store(conn, 'dev')
        self.assertEqual(await store.add_person('Synthetic'), 5)
        self.assertEqual(conn.sql[-1][1], ('Synthetic', 'dev'))
        conn.cursor = lambda: _Cursor(conn)
        await store.change_notes(5, ['tea'], {1: 'coffee'}, [])
        self.assertIn((5, 'tea', 'dev'), [p for _, p in conn.sql])
        self.assertIn(('coffee', 'dev', 1, 5), [p for _, p in conn.sql])

    async def test_main_never_protects_anyone(self):
        conn = FakeConn({'SELECT origin': [('dev',)]})
        store = Store(conn, 'main')
        self.assertFalse(await store.protected(1))
        await store.delete_person(1)
        self.assertTrue(conn.ran('DELETE FROM people'))

    async def test_dev_cannot_delete_or_rename_a_shared_person(self):
        conn = FakeConn({'SELECT origin': [('main',)], 'SELECT name': [('Synthetic',)]})
        store = Store(conn, 'dev')
        with self.assertRaises(SharedPersonError):
            await store.delete_person(2)
        with self.assertRaises(SharedPersonError):
            await store.rename(2, 'Other')
        await store.rename(2, 'Synthetic')   # 同じ名前で覚え直すだけなら通す
        self.assertFalse(conn.ran('DELETE FROM people'))
        self.assertFalse(conn.ran('UPDATE people SET name'))

    async def test_dev_can_delete_its_own_people(self):
        conn = FakeConn({'SELECT origin': [('dev',)]})
        store = Store(conn, 'dev')
        await store.delete_person(7)
        await store.rename(7, 'Other')
        self.assertTrue(conn.ran('DELETE FROM people'))
        self.assertTrue(conn.ran('UPDATE people SET name'))

    async def test_dev_cannot_unpair_or_repoint_a_shared_owner(self):
        conn = FakeConn({'secret_hash, person_id': [('h', 2)], 'SELECT person_id FROM device_owners': [(2,)],
                         'SELECT origin': [('main',)]})
        store = Store(conn, 'dev')
        self.assertFalse(await store.unpair_device('dev1', 'h'))
        with self.assertRaises(SharedPersonError):
            await store.pair_device('dev1', 'h', 9)
        await store.pair_device('dev1', 'h', 2)   # 同じ持ち主のままなら通す
        self.assertFalse(conn.ran('DELETE FROM device_owners'))


class _Cursor:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql, params=()):
        self.conn.sql.append((sql, params))


class BookScopeTests(unittest.IsolatedAsyncioTestCase):
    def book(self, scope: str, protected: bool):
        store = SimpleNamespace(scope=scope, protected=AsyncMock(return_value=protected),
                                delete_person=AsyncMock(), rename=AsyncMock())
        book = SpeakerBook(store)
        sp = SessionSpeaker(label='unknown', name='Synthetic', person_id=2, embeddings=[np.ones(192)])
        book.speakers.append(sp)
        book.last, book.last_sure = sp, True
        return book, store

    async def test_dev_refuses_to_forget_or_rename_a_shared_person(self):
        book, store = self.book('dev', True)
        self.assertIn('開発用', await book.forget('Synthetic'))
        self.assertIn('開発用', await book.rename('Other'))
        store.delete_person.assert_not_called()
        store.rename.assert_not_called()
        self.assertEqual(book.speakers[0].name, 'Synthetic')

    async def test_main_still_forgets(self):
        book, store = self.book('main', False)
        await book.forget('Synthetic')
        store.delete_person.assert_awaited_once_with(2)
        store.protected.assert_not_called()


if __name__ == '__main__':
    unittest.main()
