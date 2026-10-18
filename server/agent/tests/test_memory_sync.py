import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import numpy as np

from speakers import SpeakerBook, SessionSpeaker, Known, Judgment
from conversation import Conversation
from notes import NoteTaker


class MemorySyncTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.snapshot = {'revision': 1, 'name': 'Synthetic', 'consent': True,
                         'notes': [[1, 'tea']], 'relationship': None, 'blocked': False, 'forgets': []}
        self.versions = {1: 1}
        self.rows = [(1, 'Synthetic', [np.ones(192)], None, True, 1)]
        self.store = SimpleNamespace(
            versions=AsyncMock(side_effect=lambda: dict(self.versions)),
            load_all=AsyncMock(side_effect=lambda: list(self.rows)),
            memory_snapshot=AsyncMock(side_effect=lambda pid: self.snapshot), touch=AsyncMock())
        self.book = SpeakerBook(self.store)
        self.sp = SessionSpeaker(label='unknown', name='Synthetic', person_id=1, embeddings=[np.ones(192)])
        self.book.speakers.append(self.sp)
        self.book.last, self.book.last_sure = self.sp, True

    async def test_external_rename_and_memory_change_invalidate_cached_context(self):
        await self.book.refresh()
        self.sp.notes_context = 'old private context'
        self.sp.notes_pushed = True
        self.sp.relation_context[True] = 'old relationship'
        self.versions[1] = 2
        self.rows[0] = (1, 'Renamed', [np.ones(192)], None, True, 1)
        await self.book.refresh()
        self.assertEqual(self.sp.name, 'Renamed')
        self.assertEqual(self.sp.notes_context, '')
        self.assertEqual(self.sp.relation_context, {})
        self.assertFalse(self.sp.notes_pushed)

    async def test_external_deletion_detaches_saved_identity_and_roster(self):
        await self.book.refresh()
        registration, _ = self.book._propose_name('Synthetic', True)
        registration.speaker_id, registration.stage = self.sp.speaker_id, 'saved'
        self.versions[1] = 2
        self.rows.clear()
        await self.book.refresh()
        self.assertIsNone(self.sp.person_id)
        self.assertIsNone(self.sp.name)
        self.assertIsNone(registration.speaker_id)
        self.assertEqual(registration.stage, 'pending_identity')
        self.assertIsNone(self.book.current_person())

    async def test_newly_registered_person_is_loaded_without_reconnecting(self):
        await self.book.refresh()
        self.versions[2] = 1
        self.rows.append((2, 'Other', [np.zeros(192)], None, True, 0))
        await self.book.refresh()
        self.assertEqual([k.person_id for k in self.book.known], [1, 2])

    async def test_pending_forget_blocks_memory_for_newly_matched_speaker_and_recall(self):
        await self.book.refresh()
        self.snapshot['blocked'] = True
        line = await self.book.identify(Judgment(self.sp, True, np.ones(192), 1, .7), push_notes=True)
        self.assertNotIn('tea', line)
        self.assertTrue(self.sp.memory_suppressed)
        self.assertIn('処理中', await self.book.recall())

    async def test_failed_refresh_does_not_reinject_cached_private_memory(self):
        await self.book.refresh()
        self.sp.notes_context = 'private'
        self.store.versions.side_effect = RuntimeError('synthetic outage')
        line = await self.book.identify(Judgment(self.sp, True, np.ones(192), 1, .7), push_notes=True)
        self.assertNotIn('private', line)
        self.assertIn('確認できない', line)

    async def test_note_writer_recomputes_after_conflict_without_losing_request(self):
        with patch('openai.AsyncOpenAI'):
            taker = NoteTaker(self.book, 'test', Conversation())
        self.book.known = [Known(1, 'Synthetic', [np.ones(192)], notes_ok=True)]
        self.store.apply_notes = AsyncMock(side_effect=[False, True])
        self.store.count_notes = AsyncMock(return_value=2)
        payloads = []

        async def generate(**kwargs):
            payloads.append(json.loads(kwargs['messages'][1]['content']))
            if len(payloads) == 1:
                self.snapshot = {**self.snapshot, 'revision': 2, 'notes': [[1, 'coffee']],
                                 'forgets': [{'id': 1, 'request': 'tea', 'pending': True}], 'blocked': True}
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content='{"add": ["new preference"], "update": [], "delete": []}'))])

        taker._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=generate)))
        taker.request(1, 'new preference')
        await taker.flush()
        self.assertEqual(len(payloads), 2)
        self.assertEqual(payloads[1]['requested_notes'], ['new preference'])
        self.assertEqual(payloads[1]['existing_notes'], [{'id': 1, 'text': 'coffee'}])
        self.assertEqual(payloads[1]['forget_requests'], ['tea'])
