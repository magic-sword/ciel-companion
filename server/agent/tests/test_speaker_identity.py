"""Name registration must target one speaker and report committed storage facts."""
import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock

import numpy as np
from speakers import SpeakerBook, SessionSpeaker, Judgment
from speaker_store import Store
from tools.people import get_speaker_status, name_speaker, rename_speaker


class IdentityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.rows = {}

        async def save(name, embeddings, pid=None):
            pid = pid or 1
            self.rows[pid] = {'name': name, 'notes_consented': True, 'voice_sample_count': len(embeddings)}
            return pid

        async def identity(pid):
            return self.rows.get(pid)

        self.store = SimpleNamespace(remember_person=AsyncMock(side_effect=save), identity=AsyncMock(side_effect=identity))
        self.book = SpeakerBook(self.store)
        self.sp = SessionSpeaker(label='unknown-A', embeddings=[np.ones(192)])
        self.book.speakers.append(self.sp)
        self.book.last, self.book.last_sure = self.sp, True
        self.ctx = SimpleNamespace(userdata=SimpleNamespace(book=self.book))

    async def test_introduction_then_consent_can_use_original_label(self):
        initial_id = self.sp.speaker_id
        first = json.loads(await name_speaker(self.ctx, name='Alice', speaker='unknown-A', remember=False))
        self.assertEqual(first['status'], 'session_named')
        self.assertEqual(first['name_scope'], 'session')
        self.assertFalse(first['name_saved'])
        self.store.remember_person.assert_not_called()
        second = json.loads(await name_speaker(self.ctx, name='Alice', speaker='unknown-A', remember=True))
        self.assertEqual(second['status'], 'saved')
        self.assertTrue(second['name_saved'])
        self.assertTrue(second['voice_saved'])
        self.assertEqual(second['speaker_id'], initial_id)
        self.assertEqual(self.sp.label, 'unknown-A')
        self.assertIn('Alice', self.book.here())

    async def test_current_status_needs_no_known_name_and_queries_storage(self):
        await self.book.name('unknown-A', 'Alice', True)
        self.rows[1]['name'] = 'Persisted Alice'
        state = json.loads(await get_speaker_status(self.ctx))
        self.assertEqual(state['name'], 'Persisted Alice')
        self.assertEqual(state['name_scope'], 'persistent')
        self.assertEqual(state['voice_sample_count'], 1)
        self.rows.pop(1)
        self.assertFalse((await self.book.speaker_status())['name_saved'])

    async def test_introduction_defaults_to_current_speaker_without_persistence(self):
        result = json.loads(await name_speaker(self.ctx, name='Alice'))
        self.assertEqual(result['status'], 'session_named')
        self.assertEqual(result['speaker_id'], self.sp.speaker_id)
        self.assertFalse(result['name_saved'])
        self.store.remember_person.assert_not_called()

    async def test_save_failure_is_retryable_without_false_registered_memory(self):
        real_save = self.store.remember_person
        self.store.remember_person = AsyncMock(side_effect=RuntimeError('private error text'))
        result = await self.book.name(self.sp.speaker_id, 'Alice', True)
        self.assertEqual(result['status'], 'save_failed')
        self.assertFalse(result['name_saved'])
        self.assertIsNone(self.sp.person_id)
        self.assertEqual(self.book.known, [])
        self.store.remember_person = real_save
        self.assertEqual((await self.book.name(self.sp.speaker_id, 'Alice', True))['status'], 'saved')

    async def test_duplicate_consent_does_not_create_another_person(self):
        results = await asyncio.gather(*(self.book.name(self.sp.speaker_id, 'Alice', True) for _ in range(2)))
        self.assertEqual([r['status'] for r in results], ['saved', 'already_saved'])
        self.store.remember_person.assert_awaited_once()

    async def test_rename_waits_for_registration_to_commit(self):
        started, release = asyncio.Event(), asyncio.Event()
        save = self.store.remember_person.side_effect

        async def delayed(*args):
            started.set()
            await release.wait()
            return await save(*args)

        async def rename(pid, name):
            self.rows[pid]['name'] = name

        self.store.remember_person.side_effect = delayed
        self.store.rename = AsyncMock(side_effect=rename)
        registering = asyncio.create_task(self.book.name(self.sp.speaker_id, 'Alice', True))
        await started.wait()
        renaming = asyncio.create_task(self.book.rename('Bob'))
        await asyncio.sleep(0)
        self.store.rename.assert_not_called()
        release.set()
        await asyncio.gather(registering, renaming)
        self.assertEqual(self.sp.name, 'Bob')
        self.assertEqual(self.rows[1]['name'], 'Bob')

    async def test_other_speaker_and_ambiguous_name_are_not_modified(self):
        other = SessionSpeaker(label='other', name='Alice')
        self.book.speakers.append(other)
        self.assertEqual((await self.book.name(other.speaker_id, 'Bob', True))['status'], 'not_current_speaker')
        self.assertEqual(other.name, 'Alice')
        self.sp.name = 'Alice'
        self.assertEqual((await self.book.name('Alice', 'Bob', True))['status'], 'speaker_not_found')
        self.assertEqual((await self.book.name(self.sp.speaker_id, 'Bob', False))['status'], 'session_named')

    async def test_uncertain_speaker_does_not_get_registered(self):
        self.book.last_sure = False
        self.assertEqual((await self.book.name(self.sp.speaker_id, 'Alice', True))['status'], 'identity_uncertain')
        self.store.remember_person.assert_not_called()
        self.assertFalse((await self.book.speaker_status())['identity_certain'])

    async def test_unknown_speaker_judgment_preserves_certainty(self):
        await self.book.identify(Judgment(self.sp, True))
        self.assertTrue(self.book.last_sure)
        await self.book.identify(Judgment(self.sp, False))
        self.assertFalse(self.book.last_sure)

    async def test_no_database_and_no_voice_sample_do_not_claim_saved(self):
        self.book.store = None
        state = await self.book.name(self.sp.speaker_id, 'Alice', True)
        self.assertEqual(state['status'], 'storage_unavailable')
        self.assertFalse(state['name_saved'])
        self.book.store = self.store
        self.sp.embeddings.clear()
        self.assertEqual((await self.book.name(self.sp.speaker_id, 'Alice', True))['status'], 'need_voice_sample')
        self.store.remember_person.assert_not_called()

    async def test_status_lookup_failure_is_unknown_not_not_saved(self):
        await self.book.name(self.sp.speaker_id, 'Alice', True)
        self.store.identity.side_effect = RuntimeError
        state = await self.book.speaker_status()
        self.assertEqual(state['status'], 'storage_error')
        self.assertIsNone(state['name_saved'])
        self.assertIsNone(state['voice_saved'])

    async def test_failed_rename_does_not_modify_session_or_known_names(self):
        await self.book.name(self.sp.speaker_id, 'Alice', True)
        self.store.rename = AsyncMock(side_effect=RuntimeError)
        result = json.loads(await rename_speaker(self.ctx, 'Bob'))
        self.assertEqual(result['status'], 'rename_failed')
        self.assertEqual(self.sp.name, 'Alice')
        self.assertEqual(self.book.known[0].name, 'Alice')
        self.assertEqual(self.sp.label, 'unknown-A')

    async def test_save_confirmation_failure_is_not_reported_as_saved(self):
        real_save = self.store.remember_person.side_effect

        async def save(*args):
            pid = await real_save(*args)
            self.store.identity.side_effect = RuntimeError
            return pid

        self.store.remember_person.side_effect = save
        result = await self.book.name(self.sp.speaker_id, 'Alice', True)
        self.assertEqual(result['status'], 'save_unverified')
        self.assertIsNone(result['name_saved'])

    async def test_unavailable_or_unidentified_does_not_invent_a_name(self):
        self.book.last = None
        self.assertEqual(json.loads(await get_speaker_status(self.ctx))['status'], 'no_speaker')
        self.ctx.userdata.book = None
        self.assertFalse(json.loads(await get_speaker_status(self.ctx))['available'])


class IdentityTransactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_registration_transaction_contains_all_writes(self):
        tx = MagicMock()
        tx.__aenter__ = AsyncMock()
        tx.__aexit__ = AsyncMock(return_value=False)
        store = Store(SimpleNamespace(transaction=Mock(return_value=tx)))
        store.add_person = AsyncMock(return_value=8)
        store.add_voiceprints = AsyncMock()
        store.set_notes_consent = AsyncMock()
        self.assertEqual(await store.remember_person('Alice', []), 8)
        store.add_voiceprints.assert_awaited_once_with(8, [], None)
        store.set_notes_consent.assert_awaited_once_with(8)
        self.assertIsNone(tx.__aexit__.call_args.args[0])

    async def test_voiceprint_failure_exits_transaction_as_failure(self):
        tx = MagicMock()
        tx.__aenter__ = AsyncMock()
        tx.__aexit__ = AsyncMock(return_value=False)
        store = Store(SimpleNamespace(transaction=Mock(return_value=tx)))
        store.add_person = AsyncMock(return_value=8)
        store.add_voiceprints = AsyncMock(side_effect=RuntimeError)
        store.set_notes_consent = AsyncMock()
        with self.assertRaises(RuntimeError):
            await store.remember_person('Alice', [])
        self.assertIs(tx.__aexit__.call_args.args[0], RuntimeError)
        store.set_notes_consent.assert_not_called()
