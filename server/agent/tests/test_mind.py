import asyncio
import unittest
from unittest import mock

from livekit.agents import llm

import mind
from conversation import Conversation


class Speaker:
    def __init__(self, name):
        self.name, self.label = name, name


def history_with(*rows):
    h = Conversation()
    for role, text, who in rows:
        t = h.reserve(role=role)
        h.complete(t, text, Speaker(who) if who else None, who or '不明', sure=True)
    return h


class Style:
    def __init__(self, talk='normal'):
        self.talk = talk


class MindBuildTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch('clock.now_line', return_value='[今：朝]')
        patcher.start()
        self.addCleanup(patcher.stop)

    def livekit_ctx(self, *extra):
        ctx = llm.ChatContext()
        ctx.add_message(role='system', content='会話の指示')
        ctx.add_message(role='user', content='LiveKit だけが覚えている古い発言')
        ctx.add_message(role='assistant', content='古い返事')
        for role, text in extra:
            ctx.add_message(role=role, content=text)
        return ctx

    def test_context_comes_from_the_record(self):
        h = history_with(('user', '星を撮ったよ', 'ゆうき'), ('assistant', 'すてきなのです', None),
                         ('user', 'オリオン座だよ', 'ゆうき'))
        m = mind.Mind(h, style=Style())
        out = m.build(self.livekit_ctx(('user', '[発言者：ゆうき]\nオリオン座だよ')))
        texts = [(i.role, i.text_content) for i in out.items]
        self.assertEqual(texts[0], ('system', '会話の指示'))
        self.assertIn(('user', 'ゆうき：星を撮ったよ'), texts)
        self.assertIn(('assistant', 'すてきなのです'), texts)
        # 今回の発言は 1 回だけ（話者を添えた LiveKit の側の分）。LiveKit だけが覚えている発言は使わない
        self.assertEqual([t for r, t in texts if 'オリオン座' in t], ['[発言者：ゆうき]\nオリオン座だよ'])
        self.assertNotIn(('user', 'LiveKit だけが覚えている古い発言'), texts)
        self.assertEqual(texts[-1][1], '[発言者：ゆうき]\nオリオン座だよ')
        self.assertIn('[今：朝]', texts[-2][1])

    def test_quiet_reminder_and_memory_and_minutes(self):
        minutes = mock.Mock()
        minutes.context.return_value = '[議事録状態] {}'
        minutes.take_note.return_value = '[議事録：送った]'
        m = mind.Mind(history_with(), style=Style('quiet'), minutes=minutes, quiet_turn='呼ばれたときだけ')
        m.memory = '[覚えていること] 走るのが好き'
        notes = m.build(self.livekit_ctx(('user', 'こんにちは'))).items[-2].text_content
        for part in ('[議事録状態] {}', '[議事録：送った]', '走るのが好き', '呼ばれたときだけ'):
            self.assertIn(part, notes)

    def test_tool_calls_of_this_turn_are_kept(self):
        ctx = self.livekit_ctx(('user', '議事録とって'))
        ctx.items.append(llm.FunctionCall(call_id='c1', name='start_minutes', arguments='{}'))
        ctx.items.append(llm.FunctionCallOutput(call_id='c1', name='start_minutes', output='{}', is_error=False))
        out = mind.Mind(history_with(), style=Style()).build(ctx)
        self.assertEqual([getattr(i, 'type', None) for i in out.items[-2:]], ['function_call', 'function_call_output'])


if __name__ == '__main__':
    unittest.main()
