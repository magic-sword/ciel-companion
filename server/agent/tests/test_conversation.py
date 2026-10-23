"""外部 API・DB・Discord を呼ばず、共通履歴と利用側の境界を検証する。"""
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import tomllib
import unittest
from unittest.mock import AsyncMock, patch

from conversation import Conversation
import minutes
import notes
from persona import load_persona
from tools.conversation import search_conversation
from conversation_recording import ConversationRecorder
from turns import TurnReplies
from livekit.agents.llm import ChatMessage
from livekit.agents.voice.events import UserInputTranscribedEvent, UserStateChangedEvent, ConversationItemAddedEvent


def speaker(pid=1, name='博士'):
    return SimpleNamespace(person_id=pid, name=name, label='知らない人A')


def add(history, text, sp=None, sure=True, role='user'):
    turn = history.reserve(role=role)
    history.complete(turn, text, sp, sure=sure)
    return turn


class HistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_late_transcript_preserves_order(self):
        h = Conversation()
        first = h.reserve()
        second = add(h, 'シエルの返事', role='assistant')
        self.assertEqual(h.settled_through(), 0)
        waiter = asyncio.create_task(h.wait_pending(0, second.id))
        await asyncio.sleep(0)
        self.assertFalse(waiter.done())
        h.complete(first, '先に話したこと')
        await waiter
        self.assertEqual([t.text for t in h.between()], ['先に話したこと', 'シエルの返事'])
        self.assertEqual(h.settled_through(), second.id)

    async def test_pending_timeout_does_not_cancel_history(self):
        h = Conversation()
        turn = h.reserve()
        await h.wait_pending(0, turn.id, timeout=0.001)
        self.assertEqual(h.search('')['matches'][0]['status'], 'pending')
        h.complete(turn, '遅れて届いた')
        self.assertEqual(h.search('遅れて')['matches'][0]['text'], '遅れて届いた')

    async def test_failed_transcription_does_not_block_forever(self):
        h = Conversation()
        turn = h.reserve(time.time() - 21)
        self.assertEqual(h.settled_through(), turn.id)
        self.assertFalse(turn.ready.is_set())

    async def test_retention_and_late_completion(self):
        h = Conversation(max_turns=2, max_chars=8)
        old = h.reserve()
        add(h, '1234')
        add(h, '5678')
        h.complete(old, 'already evicted')
        self.assertEqual(h._chars, 8)
        self.assertEqual(h.dropped_through, old.id)
        add(h, '90')
        self.assertLessEqual(sum(len(t.text) for t in h.turns), 8)
        self.assertGreater(h.search('')['dropped_through'], old.id)

    async def test_correction_keeps_uncertainty_and_updates_shared_reference(self):
        h = Conversation()
        old, new = speaker(), speaker(2, '田中')
        first = add(h, '本人の発言', old)
        second = add(h, '誰かの発言', old, sure=False)
        self.assertIsNone(second.owner)
        self.assertEqual(second.name, 'たぶん博士')
        h.on_split(old, new)
        self.assertIs(second.owner, new)
        self.assertIs(first.owner, old)
        new.name = '田中さん'
        self.assertEqual(h.search('', second.id)['matches'][0]['speaker'], '田中さん')

    async def test_japanese_search_returns_context_and_changed_decision(self):
        h = Conversation()
        add(h, '集合時間は三時にしよう')
        for i in range(30):
            add(h, f'別の話題{i}')
        add(h, '集合時間はやっぱり五時に変更')
        add(h, '了解、それで確定ね', role='assistant')
        rows = h.search('集合 時間')['matches']
        self.assertTrue(any('三時' in t['text'] for t in rows))
        self.assertTrue(any('五時' in t['text'] for t in rows))
        self.assertTrue(any('確定' in t['text'] for t in rows))
        self.assertEqual([t['id'] for t in rows], sorted(t['id'] for t in rows))

    async def test_range_no_match_and_bounded_results(self):
        h = Conversation()
        for _ in range(30):
            add(h, '長い会話' * 1000)
        self.assertEqual(h.search('xyz')['matches'], [])
        result = h.search('', first_id=1, last_id=30)
        self.assertLessEqual(sum(len(t['text']) for t in result['matches']), 7000)
        self.assertTrue(result['result_clipped'])
        self.assertTrue(result['matches'][0]['text_clipped'])

    async def test_tool_returns_session_scope_and_jst(self):
        h = Conversation()
        add(h, '予算は五万円')
        result = json.loads(await search_conversation(SimpleNamespace(userdata=SimpleNamespace(history=h)), '予算'))
        self.assertEqual(result['scope'], 'current_session')
        self.assertTrue(result['matches'][0]['at'].endswith('+09:00'))


class ConsumersTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client_patch = patch('openai.AsyncOpenAI')
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.h = Conversation()

    def make_notes(self, consent=True):
        known = SimpleNamespace(person_id=1, name='博士', notes_ok=consent, note_count=0)
        store = SimpleNamespace(memory_snapshot=AsyncMock(return_value={
            'revision': 1, 'name': '博士', 'consent': True, 'notes': [], 'relationship': None,
            'forgets': [], 'blocked': False}), apply_notes=AsyncMock(return_value=True),
            count_notes=AsyncMock(return_value=1))
        taker = notes.NoteTaker(SimpleNamespace(known=[known], store=store), 'test', self.h)
        payloads = []

        async def generate(**kwargs):
            payloads.append(json.loads(kwargs['messages'][1]['content']))
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"add": [], "update": [], "delete": []}'))])

        taker._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=generate)))
        return taker, known, store, payloads

    async def test_notes_process_all_batches_including_preconsent(self):
        taker, known, store, payloads = self.make_notes(consent=False)
        sp = speaker()
        for i in range(75):
            turn = add(self.h, f'好み{i}', sp)
            taker.on_turn(turn)
        await taker.flush()
        self.assertEqual(payloads, [])
        known.notes_ok = True
        taker.on_consent(1)
        await taker.flush()
        texts = [line['text'] for p in payloads for line in p['conversation']]
        self.assertTrue(all(f'好み{i}' in texts for i in range(75)))
        self.assertEqual(taker._done[1], 75)
        self.assertTrue(all(len(p['conversation']) <= notes.CONTEXT_LINES for p in payloads))

    async def test_uncertain_speaker_is_not_personal_memory(self):
        taker, _, _, payloads = self.make_notes()
        taker.on_turn(add(self.h, 'これは別の人の好み', speaker(), sure=False))
        await taker.flush()
        self.assertEqual(payloads, [])

    async def test_notes_retry_explicit_request_after_failure(self):
        taker, _, _, payloads = self.make_notes()
        good_client = taker._client
        taker._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=RuntimeError))))
        taker.request(1, '紅茶が好き')
        await asyncio.gather(*list(taker._tasks))
        self.assertEqual(taker._requested[1], ['紅茶が好き'])
        taker._client = good_client
        await taker.flush()
        self.assertEqual(payloads[0]['requested_notes'], ['紅茶が好き'])

    async def test_very_late_transcript_is_revisited_by_notes(self):
        taker, _, _, payloads = self.make_notes()
        early = self.h.reserve(time.time() - 21)
        taker.on_turn(add(self.h, '新しい発言', speaker()))
        await taker.flush()
        self.assertEqual(taker._done[1], 2)
        self.h.complete(early, '遅れて届いた好み', speaker(), sure=True)
        taker.on_turn(early)
        await taker.flush()
        self.assertTrue(any(line['text'] == '遅れて届いた好み' for p in payloads for line in p['conversation']))

    async def test_forget_request_applies_to_every_backlog_batch(self):
        taker, _, _, payloads = self.make_notes()
        for _ in range(70):
            add(self.h, '昔の好み', speaker())
        taker.forget(1, '昔の好み')
        await taker.flush()
        self.assertGreater(len(payloads), 1)
        self.assertTrue(all('昔の好み' in p['forget_requests'] for p in payloads))

    async def test_minutes_boundaries_include_late_final_and_exclude_next_meeting(self):
        add(self.h, '開始前')
        m = minutes.Minutes(None, 'test', self.h)
        m.start()
        late = self.h.reserve()
        add(self.h, '会議の返事', role='assistant')
        written = []

        async def summarize(started, ended, previous, lines, *args):
            written.extend(minutes.conversation(lines))
            return {'title': 'テスト'}

        m._summarize = summarize
        with patch.object(minutes, 'WEBHOOK', 'unused'), patch.object(minutes, 'post_discord') as post:
            m.finish(False)
            m.start()
            add(self.h, '次の会議')
            await asyncio.sleep(0)
            self.h.complete(late, '終了直前の発言')
            await asyncio.gather(*list(m._tasks))
            self.assertEqual([r['text'] for r in written], ['終了直前の発言', '会議の返事'])
            self.assertEqual(post.call_count, 1)
            m.meeting.timer.cancel()

    async def test_minutes_roll_does_not_destroy_searchable_source(self):
        m = minutes.Minutes(None, 'test', self.h)
        m._live_update = AsyncMock(return_value={'title': '途中'})
        with patch.multiple('summaries.live', LIVE_POLL_SECONDS=0.001, LIVE_MIN_SECONDS=0, LIVE_TURNS=1):
            m.start()
            add(self.h, '予算は三万円')
            add(self.h, '承認します')
            for _ in range(20):
                if m.meeting.cursor == 2:
                    break
                await asyncio.sleep(0.002)
            self.assertTrue(m.meeting.state.has_content())
            self.assertEqual(m.meeting.cursor, 2)
            self.assertTrue(self.h.search('予算')['matches'])
            m.meeting.timer.cancel()

    async def test_minutes_roll_drains_large_backlog_in_bounded_batches(self):
        m = minutes.Minutes(None, 'test', self.h)
        m._live_update = AsyncMock(return_value={'title': '途中'})
        with patch.multiple('summaries.live', LIVE_POLL_SECONDS=0.001, LIVE_MIN_SECONDS=0, LIVE_TURNS=1):
            m.start()
            for i in range(250):
                add(self.h, f'発言{i}')
            for _ in range(200):
                if m.meeting.cursor == 250:
                    break
                await asyncio.sleep(0.002)
            self.assertEqual(m.meeting.cursor, 250)
            self.assertEqual([len(c.args[1]) for c in m._live_update.await_args_list], [40] * 6 + [10])
            m.meeting.timer.cancel()

    async def test_minutes_final_merges_long_meeting_in_bounded_batches(self):
        m = minutes.Minutes(None, 'test', self.h)
        m._summarize = AsyncMock(return_value={'title': 'まとめ'})
        m.start()
        for i in range(450):   # 全部を見直す上限（400）より多い：ライブの一覧に続きを少しずつ合わせる
            add(self.h, f'発言{i}')
        with patch.object(minutes, 'WEBHOOK', 'unused'), patch.object(minutes, 'post_discord'):
            m.finish(False)
            await asyncio.gather(*list(m._tasks))
        self.assertEqual([len(c.args[3]) for c in m._summarize.await_args_list], [100, 100, 100, 100, 50])
        self.assertEqual(m._exports[-1].stage, 'sent')

    async def test_minutes_retention_loss_is_visible(self):
        h = Conversation(max_turns=2)
        m = minutes.Minutes(None, 'test', h)
        m._summarize = AsyncMock(return_value={'title': 'テスト'})
        m.start()
        for i in range(5):
            add(h, f'発言{i}')
        with patch.object(minutes, 'WEBHOOK', 'unused'), patch.object(minutes, 'post_discord') as post:
            m.finish(False)
            await asyncio.gather(*list(m._tasks))
            self.assertIn('一部の発言が欠けています', post.call_args.args[1])

    async def test_minutes_failure_preserves_raw_draft_locally(self):
        m = minutes.Minutes(None, 'test', self.h)
        m._summarize = AsyncMock(return_value=None)
        m.start()
        add(self.h, '原文1')
        add(self.h, '原文2')
        with tempfile.TemporaryDirectory() as directory, patch.object(minutes, 'WEBHOOK', ''), patch.object(minutes, 'SAVE_DIR', Path(directory)):
            m.finish(False)
            await asyncio.gather(*list(m._tasks))
            files = list(Path(directory).glob('*.md'))
            self.assertEqual(len(files), 1)
            self.assertIn('原文1', files[0].read_text(encoding='utf-8'))

    async def test_minutes_speaker_correction_reaches_consumer(self):
        m = minutes.Minutes(None, 'test', self.h)
        m.start()
        old, new = speaker(), speaker(2, '田中')
        turn = add(self.h, '担当します', old)
        self.h.on_split(old, new)
        self.assertEqual(minutes.conversation(self.h.between(m.meeting.cursor))[0]['speaker'], '田中')
        self.assertEqual(turn.id, 1)
        m.meeting.timer.cancel()


class PersonaTests(unittest.TestCase):
    def test_conversation_prompt_is_required_and_fingerprinted(self):
        from dataclasses import replace
        p = load_persona()
        self.assertIn('search_conversation', p.conversation_instructions)
        self.assertNotEqual(p.fingerprint, replace(p, conversation_instructions='別の本文').fingerprint)

    def test_custom_config_and_missing_empty_invalid_conversation_prompt(self):
        from persona import DEFAULT_CONFIG
        config = tomllib.loads(DEFAULT_CONFIG.read_text(encoding='utf-8'))
        config = {k: str(DEFAULT_CONFIG.parent / value) for k, value in config.items()}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = root / 'conversation.md'
            config['conversation_instructions_file'] = str(prompt)
            custom = root / 'persona.toml'
            custom.write_text('\n'.join(f'{k} = {json.dumps(v)}' for k, v in config.items()), encoding='utf-8')
            with patch.dict(os.environ, {'CIEL_PERSONA_CONFIG': str(custom)}):
                with self.assertRaises(ValueError):
                    load_persona()
                prompt.write_text(' ', encoding='utf-8')
                with self.assertRaises(ValueError):
                    load_persona()
                prompt.write_bytes(b'\xff\xfe')
                with self.assertRaises(ValueError):
                    load_persona()
                prompt.write_text('search_conversation', encoding='utf-8')
                self.assertEqual(load_persona().conversation_instructions, 'search_conversation')


class RecordingTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_handoff_is_not_recorded_as_speech(self):
        from livekit.agents.llm import AgentHandoff
        self.recorder.on_item(ConversationItemAddedEvent(item=AgentHandoff(new_agent_id='ciel')))
        self.assertEqual(self.h.turns, [])

    def setUp(self):
        self.h = Conversation()
        self.replies = TurnReplies(SimpleNamespace(), None, None, SimpleNamespace(talk='normal'), '', history=self.h)
        self.recorder = ConversationRecorder(self.h, self.replies)

    def segment(self, at):
        self.replies.on_user_state(UserStateChangedEvent(old_state='listening', new_state='speaking', created_at=at))
        self.replies.on_user_state(UserStateChangedEvent(old_state='speaking', new_state='listening', created_at=at + 0.5))

    def transcript(self, item_id, text, at):
        self.recorder.on_transcribed(UserInputTranscribedEvent(item_id=item_id, transcript=text, is_final=True))
        self.recorder.on_item(ConversationItemAddedEvent(item=ChatMessage(
            id=item_id, role='user', content=[text], created_at=at, metrics={'started_speaking_at': at})))

    async def test_reversed_transcript_events_use_speech_start_time(self):
        at = time.time() - 4
        self.segment(at)
        first_person = speaker(1, '博士')
        first_judgment = asyncio.get_running_loop().create_future()
        first_judgment.set_result(SimpleNamespace(sp=first_person, sure=True))
        self.replies._segments[-1].judgment = first_judgment
        self.segment(at + 2)
        second_person = speaker(2, '田中')
        second_judgment = asyncio.get_running_loop().create_future()
        second_judgment.set_result(SimpleNamespace(sp=second_person, sure=True))
        self.replies._segments[-1].judgment = second_judgment
        self.transcript('second', '後の発言', at + 2)
        self.transcript('first', '先の発言', at)
        await self.recorder.flush()
        self.assertEqual([t.text for t in self.h.turns], ['先の発言', '後の発言'])
        self.assertEqual([t.source_id for t in self.h.turns], ['first', 'second'])
        self.assertEqual([t.owner for t in self.h.turns], [first_person, second_person])
        self.transcript('first', '先の発言', at)
        await self.recorder.flush()
        self.assertEqual(len(self.h.turns), 2)

    async def test_unmatched_timestamp_does_not_steal_another_speakers_segment(self):
        at = time.time() - 3
        self.segment(at)
        self.assertIsNone(self.replies.take_segment(at - 5))
        self.assertIsNotNone(self.replies.take_segment(at))

    async def test_missing_provider_id_falls_back_and_assistant_is_cleaned_once(self):
        self.segment(time.time() - 1)
        self.recorder.on_transcribed(UserInputTranscribedEvent(transcript='声の内容', is_final=True))
        item = ConversationItemAddedEvent(item=ChatMessage(id='reply', role='assistant', content=['[happy] うん。[silent]']))
        self.recorder.on_item(item)
        self.recorder.on_item(item)
        await self.recorder.flush()
        self.assertEqual([t.text for t in self.h.turns], ['声の内容', 'うん。'])


if __name__ == '__main__':
    unittest.main()
