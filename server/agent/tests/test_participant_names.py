"""Meeting roster acceptance is independent from speaker confirmation and persistence."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import numpy as np
from speakers import SpeakerBook, SessionSpeaker
from tools.people import register_participant_name, confirm_participant_name, people_here
from tools.people import not_this_speaker
from conversation import Conversation
from turns import TurnReplies, Segment
from speakers import Judgment, Known
from tools.memory import forget_about_speaker
import test_speaker_identity as fixtures


class ParticipantNameTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixtures.IdentityTests.setUp

    def switch(self, label='unknown-B', sure=True):
        sp = SessionSpeaker(label=label, embeddings=[np.ones(192)])
        self.book.speakers.append(sp)
        self.book.last, self.book.last_sure = sp, sure
        return sp

    def source(self, text):
        h = Conversation()
        t = h.reserve()
        h.complete(t, text)
        self.book.current_turns = [t]

    async def test_short_self_introduction_is_accepted_without_a_speaker(self):
        self.book.last = None
        result = await self.book.register_name('Bob', True)
        self.assertEqual(result['status'], 'pending_identity')
        self.assertIsNone(result['bound_speaker_id'])
        self.assertEqual(result['proposed_name'], 'Bob')
        self.assertEqual(len((await self.book.speaker_status())['name_registrations']), 1)
        self.store.remember_person.assert_not_called()

    async def test_legacy_temporary_name_call_also_keeps_pending_name(self):
        self.book.last = None
        first = await self.book.name('', 'Bob', False)
        self.book.last, self.book.last_sure = self.sp, False
        second = await self.book.name('', 'Bob', False)
        self.assertEqual(first['status'], 'pending_identity')
        self.assertEqual(first['registration_id'], second['registration_id'])
        self.assertIsNone(self.sp.name)

    async def test_introducer_is_not_named_or_allowed_to_confirm(self):
        result = await self.book.register_name('Bob')
        entry_id = result['registration_id']
        self.assertIsNone(self.sp.name)
        self.assertEqual(result['introduced_by'], self.sp.speaker_id)
        result = await self.book.confirm_name(entry_id, 'Bob', True)
        self.assertEqual(result['status'], 'introduced_person_must_confirm')
        self.store.remember_person.assert_not_called()

    async def test_uncertain_introducer_candidate_cannot_confirm_its_own_introduction(self):
        self.book.last_sure = False
        entry = await self.book.register_name('Bob')
        self.book.last_sure = True
        result = await self.book.confirm_name(entry['registration_id'], 'Bob', True)
        self.assertEqual(result['status'], 'introduced_person_must_confirm')
        self.store.remember_person.assert_not_called()

    async def test_introduced_person_self_introduction_reuses_id_without_saving(self):
        introduced = await self.book.register_name('Bob')
        bob = self.switch()
        confirmed = await self.book.register_name('Bob', True)
        self.assertEqual(confirmed['registration_id'], introduced['registration_id'])
        self.assertEqual(confirmed['status'], 'session_named')
        self.assertEqual(confirmed['bound_speaker_id'], bob.speaker_id)
        self.assertEqual(bob.name, 'Bob')
        self.assertIsNone(self.sp.name)
        self.store.remember_person.assert_not_called()

    async def test_confirmation_and_consent_are_separate(self):
        entry = await self.book.register_name('Bob')
        bob = self.switch()
        first = await self.book.confirm_name(entry['registration_id'], 'Bob')
        self.assertEqual(first['registration_state'], 'session_named')
        self.assertFalse(first['name_saved'])
        self.store.remember_person.assert_not_called()
        saved = await self.book.confirm_name(entry['registration_id'], 'Bob', True)
        self.assertEqual(saved['registration_state'], 'saved')
        self.assertTrue(saved['voice_saved'])
        self.assertEqual(bob.person_id, 1)

    async def test_uncertain_consent_is_not_carried_forward(self):
        entry = await self.book.register_name('Bob')
        self.switch(sure=False)
        pending = await self.book.confirm_name(entry['registration_id'], 'Bob', True)
        self.assertEqual(pending['status'], 'pending_identity')
        self.assertIsNone(pending['bound_speaker_id'])
        self.book.last_sure = True
        result = await self.book.confirm_name(entry['registration_id'], 'Bob')
        self.assertEqual(result['registration_state'], 'session_named')
        self.store.remember_person.assert_not_called()

    async def test_bound_registration_cannot_be_saved_by_a_different_speaker(self):
        first = await self.book.register_name('Alice', True)
        self.switch()
        result = await self.book.confirm_name(first['registration_id'], 'Alice', True)
        self.assertEqual(result['status'], 'not_current_speaker')
        self.store.remember_person.assert_not_called()

    async def test_save_failure_keeps_confirmed_session_binding(self):
        result = await self.book.register_name('Alice', True)
        real_save = self.store.remember_person
        self.store.remember_person = AsyncMock(side_effect=RuntimeError)
        failed = await self.book.confirm_name(result['registration_id'], 'Alice', True)
        self.assertEqual(failed['status'], 'save_failed')
        self.assertEqual(failed['registration_state'], 'session_named')
        self.assertEqual(failed['bound_speaker_id'], self.sp.speaker_id)
        self.assertIsNone(self.sp.person_id)
        self.store.remember_person = real_save
        self.assertEqual((await self.book.confirm_name(result['registration_id'], 'Alice', True))['status'], 'saved')

    async def test_name_conflict_and_wrong_confirmed_name_do_not_overwrite(self):
        self.sp.name = 'Alice'
        entry = await self.book.register_name('Bob', True)
        self.assertEqual(entry['status'], 'name_conflict')
        result = await self.book.confirm_name(entry['registration_id'], 'Carol')
        self.assertEqual(result['status'], 'name_mismatch')
        self.assertEqual(self.sp.name, 'Alice')

    async def test_duplicate_and_same_named_participants_require_correct_ids(self):
        first = await self.book.register_name('Bob')
        same = await self.book.register_name('Bob')
        self.assertEqual(first['registration_id'], same['registration_id'])
        self.switch('introducer-C')
        other = await self.book.register_name('Bob')
        self.assertNotEqual(first['registration_id'], other['registration_id'])
        self.switch('Bob')
        self.assertEqual((await self.book.register_name('Bob', True))['status'], 'ambiguous_name')
        result = await self.book.confirm_name(first['registration_id'], 'Bob')
        self.assertEqual(result['status'], 'session_named')
        self.assertIsNone(self.book.name_registrations[other['registration_id']].speaker_id)

    async def test_no_automatic_binding_on_next_speaker_and_roster_is_session_only(self):
        await self.book.register_name('Bob')
        self.switch()
        roster = self.book.roster()
        self.assertIsNone(roster['registrations'][0]['bound_speaker_id'])
        self.assertEqual(SpeakerBook(None).roster()['registrations'], [])

    async def test_roster_limit_and_missing_id_are_explicit(self):
        for i in range(64):
            await self.book.register_name(f'Person{i}')
        self.assertEqual((await self.book.register_name('Overflow'))['status'], 'registration_limit')
        self.assertEqual((await self.book.confirm_name('missing', 'Bob'))['status'], 'registration_not_found')
        self.assertEqual((await self.book.register_name(''))['status'], 'invalid_name')

    async def test_introduced_name_honorific_is_normalized_without_binding(self):
        result = await self.book.register_name('田中さん')
        self.assertEqual(result['proposed_name'], '田中')
        self.assertIsNone(result['bound_speaker_id'])

    async def test_rename_and_forget_update_registration(self):
        result = await self.book.register_name('Alice', True)
        await self.book.rename('Bob')
        self.assertEqual(self.book.roster()['registrations'][0]['proposed_name'], 'Bob')
        saved = await self.book.confirm_name(result['registration_id'], 'Bob', True)
        self.assertEqual(saved['registration_state'], 'saved')
        self.store.delete_person = AsyncMock()
        await self.book.forget('Bob')
        entry = self.book.roster()['registrations'][0]
        self.assertEqual(entry['registration_state'], 'pending_identity')
        self.assertIsNone(entry['bound_speaker_id'])

    async def test_tools_return_ids_and_roster_without_side_effects(self):
        introduced = json.loads(await register_participant_name(self.ctx, 'Bob'))
        roster = json.loads(await people_here(self.ctx))
        self.assertEqual(roster['registrations'][0]['registration_id'], introduced['registration_id'])
        self.switch()
        self.source('私はBobです。')
        result = json.loads(await confirm_participant_name(self.ctx, introduced['registration_id'], 'Bob'))
        self.assertEqual(result['status'], 'session_named')
        self.store.remember_person.assert_not_called()
        self.ctx.userdata.book = None
        self.assertFalse(json.loads(await register_participant_name(self.ctx, 'Bob'))['available'])

    async def test_source_overrides_misclassified_introduction_and_blocks_premature_confirmation(self):
        self.source('こちらは田中さんです。')
        result = json.loads(await register_participant_name(self.ctx, '田中', True))
        self.assertEqual(result['source'], 'introduced')
        self.assertEqual(result['status'], 'pending_identity')
        self.assertIsNone(self.sp.name)
        blocked = json.loads(await confirm_participant_name(self.ctx, result['registration_id'], '田中', True))
        self.assertEqual(blocked['status'], 'introduced_person_must_confirm')
        self.store.remember_person.assert_not_called()

    async def test_self_introduction_without_source_text_remains_unbound(self):
        self.book.current_turns = []
        result = json.loads(await register_participant_name(self.ctx, '田中', True))
        self.assertEqual(result['status'], 'pending_identity')
        self.assertIsNone(self.sp.name)
        self.source('シエル、私が田中です。')
        result = json.loads(await confirm_participant_name(self.ctx, result['registration_id'], '田中'))
        self.assertEqual(result['status'], 'session_named')

    async def test_third_party_introduction_cannot_trigger_identity_split(self):
        self.book.split = AsyncMock()
        h = Conversation()
        for text in ['こちらは田中です。', 'こちらは 田中です。', '田中さんの声を覚えてあげて。']:
            turn = h.reserve()
            h.complete(turn, text)
            self.book.current_turns = [turn]
            result = json.loads(await not_this_speaker(self.ctx, '田中'))
            self.assertEqual(result['status'], 'correction_unverified')
        self.book.split.assert_not_called()

    async def test_explicit_self_correction_uses_actual_source_utterance(self):
        self.book.split = AsyncMock(return_value='corrected')
        h = Conversation()
        turn = h.reserve()
        h.complete(turn, 'えっと、私は田中です。')
        self.book.current_turns = [turn]
        self.assertEqual(await not_this_speaker(self.ctx, '田中'), 'corrected')
        self.book.split.assert_awaited_once_with('田中')
        self.book.current_turns = []
        result = json.loads(await not_this_speaker(self.ctx, '田中'))
        self.assertEqual(result['status'], 'correction_unverified')

    async def test_harness_exposes_only_the_reply_source_and_clears_stale_source(self):
        h = Conversation()
        old, current = h.reserve(1), h.reserve(10)
        h.complete(old, '私は田中です。')
        h.complete(current, 'こちらは田中です。')
        replies = TurnReplies(SimpleNamespace(generate_reply=Mock()), self.book, None,
                              SimpleNamespace(talk='normal', presence='close'), '')
        replies.encoder = object()
        replies._judgment_for = AsyncMock(return_value=Judgment(self.sp, True))
        replies._recent.extend([Segment(1, 2, None, old), Segment(10, 12, None, current)])
        await replies._reply(10, 12)
        self.assertEqual(self.book.current_turns, [current])
        self.book.split = AsyncMock()
        self.assertEqual(json.loads(await not_this_speaker(self.ctx, '田中'))['status'], 'correction_unverified')
        self.book.split.assert_not_called()
        replies.encoder = None
        await replies._reply(13, 14)
        self.assertEqual(self.book.current_turns, [])

    async def test_memory_context_survives_multiple_replies_but_is_hidden_in_public(self):
        self.sp.person_id, self.sp.name = 1, 'Alice'
        self.book.known = [Known(1, 'Alice', [], notes_ok=True, note_count=1)]
        self.store.touch = AsyncMock()
        self.store.notes = AsyncMock(return_value=[(1, 'private remembered fact')])
        self.store.relationship = AsyncMock(return_value=None)
        j = Judgment(self.sp, True)
        first = await self.book.identify(j, push_notes=True)
        second = await self.book.identify(j, push_notes=True)
        public = await self.book.identify(j, push_notes=False)
        self.assertIn('private remembered fact', first)
        self.assertIn('private remembered fact', second)
        self.assertNotIn('private remembered fact', public)
        self.store.notes.assert_awaited_once()
        self.store.rename = AsyncMock()
        await self.book.rename('NewAlice')
        renamed = await self.book.identify(j, push_notes=True)
        self.assertIn('NewAlice', renamed)
        self.assertEqual(self.store.notes.await_count, 2)
        self.ctx.userdata.notes = SimpleNamespace(forget=Mock())
        await forget_about_speaker(self.ctx, 'private remembered fact')
        after = await self.book.identify(j, push_notes=True)
        self.assertNotIn('private remembered fact', after)
