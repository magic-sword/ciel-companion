"""Generic summaries: templates, item kinds, live diffs with stable IDs, final replace, app packets."""
import asyncio
import json
from datetime import datetime
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

from conversation import Conversation
from jst import JST
import minutes
from summaries import kinds, live, templates
from summaries.state import SummaryState


class TemplateTests(unittest.TestCase):
    def test_shipped_templates_load(self):
        loaded = templates.load()
        self.assertEqual(set(loaded), {'meeting', 'goals', 'research'})
        self.assertEqual([s.kind for s in loaded['meeting'].sections], ['topic', 'decision', 'action', 'question'])
        self.assertTrue(all(t.guide for t in loaded.values()))

    def test_bad_template_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'meeting.md').write_text('guide', encoding='utf-8')
            Path(d, 'meeting.toml').write_text(
                'label = "x"\nguide_file = "meeting.md"\n[[sections]]\nid = "a"\nlabel = "A"\nkind = "poem"\n',
                encoding='utf-8')
            with self.assertRaises(ValueError):
                templates.load(Path(d))


class KindTests(unittest.TestCase):
    def test_clean_keeps_only_known_fields(self):
        self.assertIsNone(kinds.clean('decision', {'text': '  '}))
        self.assertEqual(kinds.clean('decision', {'text': 'OK', 'secret': 1}), {'text': 'OK'})
        action = kinds.clean('action', {'text': '資料', 'who': 'ミナ', 'done': 'yes'})
        self.assertEqual(action, {'text': '資料', 'who': 'ミナ', 'due': '', 'done': False})

    def test_finding_sources_must_come_from_research(self):
        raw = {'text': '速い', 'sources': [{'title': 'a', 'url': 'https://example.org/a'},
                                          {'title': 'b', 'url': 'https://invented.example/b'},
                                          {'title': 'c', 'url': 'javascript:alert(1)'}]}
        item = kinds.clean('finding', raw, {'https://example.org/a', 'javascript:alert(1)'})
        self.assertEqual(item['sources'], [{'title': 'a', 'url': 'https://example.org/a'}])

    def test_meeting_rendering_matches_previous_minutes(self):
        self.assertEqual(kinds.render('action', {'text': '見積もりを出す。', 'who': 'ミナ', 'due': '10/30'}),
                         ['- 見積もりを出す（ミナ、10/30 まで）'])
        self.assertEqual(kinds.render('action', {'text': '連絡', 'who': '', 'due': ''}), ['- 連絡（担当未定）'])
        self.assertEqual(kinds.render('topic', {'text': '予算', 'points': ['三万円']}), ['### 予算', '- 三万円'])


class StateTests(unittest.TestCase):
    def setUp(self):
        self.state = SummaryState(templates.load()['meeting'])

    def test_ops_keep_ids_and_mark_changed_items(self):
        changed = self.state.apply({'title': '定例', 'current_topic': '予算', 'ops': [
            {'op': 'add', 'section': 'decisions', 'item': {'text': '三万円で進める'}},
            {'op': 'add', 'section': 'actions', 'item': {'text': '見積もり', 'who': 'ミナ'}},
            {'op': 'add', 'section': 'nope', 'item': {'text': 'x'}},
            {'op': 'add', 'section': 'decisions', 'item': {'text': '三万円で進める'}}]})
        self.assertEqual(changed, 4)
        decision = self.state.items['decisions'][0]
        self.assertEqual((decision['id'], decision['rev']), ('decisions-1', 1))
        self.state.apply({'ops': [{'op': 'update', 'id': 'actions-2', 'item': {'due': '金曜'}},
                                  {'op': 'remove', 'id': 'missing'}]})
        action = self.state.items['actions'][0]
        self.assertEqual((action['who'], action['due'], action['rev']), ('ミナ', '金曜', 2))
        self.assertEqual(self.state.items['decisions'][0]['rev'], 1)   # untouched items keep their rev
        self.assertEqual(self.state.apply({'ops': [{'op': 'update', 'id': 'actions-2', 'item': {'due': '金曜'}}]}), 0)
        self.state.apply({'ops': [{'op': 'remove', 'id': 'decisions-1'}]})
        self.assertEqual(self.state.items['decisions'], [])

    def test_replace_keeps_matching_ids(self):
        self.state.apply({'ops': [{'op': 'add', 'section': 'decisions', 'item': {'text': 'A'}},
                                  {'op': 'add', 'section': 'decisions', 'item': {'text': 'B'}}]})
        self.state.replace({'title': '清書', 'summary': '要点', 'attendees': ['ミナ', ''],
                            'sections': {'decisions': [{'id': 'decisions-1', 'text': 'A'},
                                                       {'id': 'decisions-2', 'text': 'B を直した'},
                                                       {'text': 'C'}, {'id': 'decisions-1', 'text': 'dup'}]}})
        ids = [(i['id'], i['rev']) for i in self.state.items['decisions']]
        self.assertEqual(ids[0], ('decisions-1', 1))
        self.assertEqual(ids[1], ('decisions-2', 2))
        self.assertNotIn(ids[2][0], ('decisions-1', 'decisions-2'))
        self.assertNotEqual(ids[3][0], 'decisions-1')
        self.assertEqual(self.state.attendees, ['ミナ'])
        text = self.state.render(datetime(2026, 10, 23, 10, 0, tzinfo=JST), datetime(2026, 10, 23, 11, 0, tzinfo=JST))
        self.assertIn('# 清書\n2026-10-23（金） 10:00〜11:00\n参加者：ミナ\n\n## 概要\n要点\n\n## 決まったこと\n- A', text)

    def test_app_shape_is_uniform(self):
        self.state.apply({'ops': [{'op': 'add', 'section': 'topics', 'item': {'text': '予算', 'points': ['x']}}]})
        app = self.state.for_app()
        item = app['sections'][0]['items'][0]
        self.assertEqual(set(item), {'id', 'rev', 'text', 'points', 'who', 'due', 'done', 'status', 'sources'})


class PolicyTests(unittest.TestCase):
    def test_updates_follow_conversation_volume(self):
        self.assertFalse(live.due(0, 999, force=True))
        self.assertTrue(live.due(1, 0, force=True))
        self.assertFalse(live.due(10, live.LIVE_MIN_SECONDS - 1))
        self.assertTrue(live.due(live.LIVE_TURNS, live.LIVE_MIN_SECONDS))
        self.assertFalse(live.due(1, 999))
        self.assertTrue(live.due(2, live.LIVE_IDLE_SECONDS))
        self.assertFalse(live.due(2, live.LIVE_IDLE_SECONDS - 1))


class LiveTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        p = patch('minutes.openai.AsyncOpenAI')
        p.start()
        self.addCleanup(p.stop)
        self.h = Conversation()
        self.m = minutes.Minutes(None, 'final', self.h, 'live')
        self.sent, self.progress = [], []
        self.m.on_state, self.m.on_progress = self.sent.append, self.progress.append
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for target, value in [('minutes.WEBHOOK', ''), ('minutes.SAVE_DIR', Path(self.tmp.name))]:
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)

    async def asyncTearDown(self):
        await self.m.flush()

    def add(self, text):
        t = self.h.reserve()
        self.h.complete(t, text)
        return t

    async def test_unknown_template_is_refused(self):
        self.assertEqual(self.m.start(template='poem'), minutes.UNKNOWN_TEMPLATE)
        self.assertFalse(self.m.recording)
        self.assertEqual(self.m.start(template='goals'), minutes.STARTED)
        self.assertEqual(self.sent[-1]['label'], '目標と計画')
        self.assertTrue(self.sent[-1]['recording'])

    async def test_live_update_waits_for_enough_talk_then_publishes(self):
        self.m._live_update = AsyncMock(return_value={'current_topic': '予算', 'ops': [
            {'op': 'add', 'section': 'decisions', 'item': {'text': '三万円'}}]})
        self.m.start()
        m = self.m.meeting
        self.add('こんにちは')
        self.assertFalse(await self.m._update(m))   # one turn, just started: wait
        self.assertEqual(self.progress[-1]['pending_turns'], 1)
        m.updated_at = time.monotonic() - live.LIVE_IDLE_SECONDS
        self.add('三万円で進めましょう')
        self.assertTrue(await self.m._update(m))
        self.assertEqual(m.cursor, 2)
        state = self.sent[-1]
        self.assertEqual(state['current_topic'], '予算')
        self.assertEqual(state['sections'][1]['items'][0]['text'], '三万円')
        self.assertEqual(state['pending_turns'], 0)
        self.assertGreater(state['updated_at'], 0)

    async def test_refresh_updates_now_and_failures_do_not_advance(self):
        self.m._live_update = AsyncMock(return_value=None)
        self.m.start()
        self.add('一つだけ')
        self.m.refresh()
        await asyncio.gather(*list(self.m._tasks))
        self.assertEqual(self.m.meeting.cursor, 0)
        self.m._live_update = AsyncMock(return_value={'ops': []})
        self.m.meeting.updated_at = 0
        self.m.refresh()
        await asyncio.gather(*list(self.m._tasks))
        self.assertEqual(self.m.meeting.cursor, 1)

    async def test_research_sources_become_allowed_for_findings(self):
        record = self.h.research.begin('最近のAI', None, 'call')
        record.status, record.summary = 'completed', '要約'
        record.sources = [{'number': 1, 'title': '資料', 'url': 'https://example.org/ai'}]
        record.requested_at = time.time() + 1
        self.m._live_update = AsyncMock(return_value={'ops': [{'op': 'add', 'section': 'findings', 'item': {
            'text': '新しいモデル', 'sources': [{'title': '資料', 'url': 'https://example.org/ai'},
                                           {'title': 'x', 'url': 'https://made.up/x'}]}}]})
        self.m.start(template='research')
        self.add('調べて')
        self.add('なるほど')
        self.assertTrue(await self.m._update(self.m.meeting, force=True))
        self.assertEqual(self.m._live_update.await_args.args[2][0]['question'], '最近のAI')
        finding = self.m.meeting.state.items['findings'][0]
        self.assertEqual(finding['sources'], [{'title': '資料', 'url': 'https://example.org/ai'}])

    async def test_finish_publishes_stages_and_final_result(self):
        self.m._summarize = AsyncMock(return_value={'title': '清書', 'sections': {'decisions': [{'text': '決定'}]}})
        self.m.start()
        self.add('一')
        self.add('二')
        self.m.finish(False)
        await asyncio.gather(*list(self.m._tasks))
        stages = [s['stage'] for s in self.sent]
        self.assertIn('building', stages)
        self.assertEqual(self.sent[-1]['stage'], 'saved_locally')
        self.assertFalse(self.sent[-1]['recording'])
        self.assertEqual(self.sent[-1]['title'], '清書')
        self.assertEqual(self.m._summarize.await_args.args[4].name, 'meeting')

    async def test_packets_split_and_rejoin(self):
        state = {'title': 'あ' * 5000, 'sections': []}
        parts = minutes.packets(state, 7)
        self.assertEqual(len(parts), len(json.dumps(state, ensure_ascii=False)) // minutes.PART_CHARS + 1)
        self.assertTrue(all(len(json.dumps(p, ensure_ascii=False).encode('utf-8')) < 15000 for p in parts))
        self.assertEqual(json.loads(''.join(p['text'] for p in parts)), state)


if __name__ == '__main__':
    unittest.main()
