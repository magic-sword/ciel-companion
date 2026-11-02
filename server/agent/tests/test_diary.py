"""Ciel's own diary: only what really happened to her, kept without anyone's name, and given to the thinker."""
import asyncio
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from conversation import Conversation
import diary
from initiative import Initiative
from jst import JST
import touch


NOW = datetime(2026, 11, 3, 15, 0, tzinfo=JST)


class DiaryTests(unittest.IsolatedAsyncioTestCase):
    def test_ago_reads_like_speech(self):
        self.assertEqual(diary.ago(NOW - timedelta(minutes=5), NOW), 'さっき')
        self.assertEqual(diary.ago(NOW - timedelta(hours=3), NOW), '今日')
        self.assertEqual(diary.ago(NOW - timedelta(days=1), NOW), 'きのう')
        self.assertEqual(diary.ago(NOW - timedelta(days=4), NOW), '4 日前')
        self.assertEqual(diary.ago(NOW - timedelta(days=60), NOW), 'ずっと前')

    async def test_added_events_are_saved_and_listed_oldest_first(self):
        store = SimpleNamespace(add_ciel_event=AsyncMock(), ciel_events=AsyncMock(return_value=[
            (7, NOW - timedelta(days=2), 'song', '歌を最後まで聴かせてもらった（1:30）')]))
        d = diary.Diary(store)
        await d.load()
        d.add('research', '気になって調べた：サモエドの毛が白い理由\n→ 寒い地方で…' + 'あ' * 200, at=NOW)
        await asyncio.sleep(0)
        store.add_ciel_event.assert_awaited_once()
        kind, text, keep = store.add_ciel_event.await_args.args
        self.assertEqual((kind, keep), ('research', diary.KEEP))
        self.assertEqual(len(text), diary.TEXT_CHARS)
        self.assertNotIn('\n', text)
        lines = d.lines(NOW)
        self.assertEqual(lines[0], '2 日前：歌を最後まで聴かせてもらった（1:30）')
        self.assertTrue(lines[1].startswith('さっき：気になって調べた：'))

    async def test_without_a_db_it_remembers_for_this_conversation_only(self):
        d = diary.Diary()
        await d.load()
        for i in range(diary.SHOW + 2):
            d.add('touch', f'頭をなでてもらった{i}', at=NOW)
        self.assertEqual(len(d.lines(NOW)), diary.SHOW)
        d.add('touch', '   ')
        self.assertEqual(len(d.events), diary.SHOW)

    async def test_a_failing_db_keeps_the_conversation_going(self):
        d = diary.Diary(SimpleNamespace(ciel_events=AsyncMock(side_effect=RuntimeError),
                                        add_ciel_event=AsyncMock(side_effect=RuntimeError)))
        await d.load()
        d.add('song', '歌を最後まで聴かせてもらった（0:40）', at=NOW)
        await asyncio.sleep(0)
        self.assertEqual(len(d.events), 1)


class TouchDiaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_touch_is_noted_once_per_conversation_without_who(self):
        session = SimpleNamespace(user_state='listening', agent_state='listening')
        t = touch.TouchReactions(session)
        t.diary = Mock()

        def send(gesture, phase):
            t.on_data(SimpleNamespace(topic=touch.TOPIC, data=json.dumps(
                {'part': 'head', 'gesture': gesture, 'phase': phase, 'duration_ms': 1200}).encode()))
        send('stroke', 'start')
        send('stroke', 'end')
        send('stroke', 'start')
        send('tap', 'once')
        self.assertEqual([c.args for c in t.diary.add.call_args_list],
                         [('touch', '頭をなでてもらった'), ('touch', '頭をちょんとつつかれた')])
        if t._timer is not None:
            t._timer.cancel()


class ThinkerGetsEventsTests(unittest.IsolatedAsyncioTestCase):
    async def test_events_go_to_the_thinker(self):
        session = SimpleNamespace(generate_reply=Mock())
        i = Initiative(session, SimpleNamespace(talk='chatty'), 'NUDGE', history=Conversation(), instructions='THINK')
        i.diary = diary.Diary()
        i.diary.add('research', '気になって調べた：サモエドの毛が白い理由', at=datetime.now(JST))
        reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))])
        i._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=reply))))
        await i._think(0.0)
        request = json.loads(i._client.chat.completions.create.await_args.kwargs['messages'][1]['content'])
        self.assertEqual(request['ciel_events'], ['さっき：気になって調べた：サモエドの毛が白い理由'])
        i.apply({'thoughts': [{'text': '白い毛の理由、話したい', 'kind': 'share', 'stimulus': '調べたこと', 'motivation': 4}]}, 1.0)
        self.assertEqual(i.thoughts[0].kind, 'share')


if __name__ == '__main__':
    unittest.main()
