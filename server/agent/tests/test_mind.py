import asyncio
import time
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


class TalkerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = mock.patch('clock.now_line', return_value='[今：朝]')
        patcher.start()
        self.addCleanup(patcher.stop)

    async def collect(self, m, parts):
        async def stream():
            for p in parts:
                yield p
        return [c async for c in m.talk(stream())]

    async def test_talker_gets_short_instructions_and_the_brief(self):
        m = mind.Mind(history_with(), style=Style())
        m.apply_brief({'topic': '展示', 'decided': 'A2 で印刷'}, through=3)
        ctx = llm.ChatContext()
        ctx.add_message(role='system', content='全部の指示')
        ctx.add_message(role='user', content='どう思う？')
        out = m.build(ctx, talker_instructions='短い指示')
        texts = [i.text_content for i in out.items]
        self.assertEqual(texts[0], '短い指示')
        self.assertNotIn('全部の指示', texts)
        self.assertIn('[今のまとめ]\n話題：展示\n決まったこと：A2 で印刷', texts[-2])

    async def test_think_hands_over_to_the_mind(self):
        said, thought = [], []
        m = mind.Mind(history_with(), say=lambda why, **kw: said.append((why, kw)), think=lambda: thought.append(1),
                      turn_instructions='考える番')
        self.assertEqual(await self.collect(m, ['[th', 'ink]', 'ignored']), [])
        self.assertEqual(said, [('mind', {'instructions': '考える番', 'tool_choice': 'auto'})])
        self.assertEqual(thought, [1])
        # 口が「mind」で頼んだ次の返事は、心が作る（1 回だけ）
        m.on_say('mind')
        self.assertTrue(m.deep_turn(llm.ChatContext()))
        self.assertFalse(m.deep_turn(llm.ChatContext()))

    async def test_ordinary_and_emotion_tagged_replies_flow(self):
        m = mind.Mind(history_with(), say=lambda *a, **k: self.fail('handed over'))
        self.assertEqual(await self.collect(m, ['[think', 'ing]えっと', '…']), ['[think', 'ing]えっと', '…'])
        self.assertEqual(await self.collect(m, ['[happy]', 'わあ']), ['[happy]', 'わあ'])
        self.assertEqual(await self.collect(m, ['[silent]']), ['[silent]'])

    async def test_tool_results_go_to_the_mind(self):
        ctx = llm.ChatContext()
        ctx.add_message(role='user', content='議事録とって')
        ctx.items.append(llm.FunctionCallOutput(call_id='c1', name='start_minutes', output='{}', is_error=False))
        self.assertTrue(mind.Mind(history_with()).deep_turn(ctx))

    async def test_brief_is_written_when_enough_was_said(self):
        h = history_with(*[('user', f'発言{i}', 'ゆうき') for i in range(6)])
        m = mind.Mind(h, style=Style(), brief_instructions='まとめて')
        m._brief_at -= 100
        with mock.patch.object(m, '_write_brief', mock.AsyncMock()) as write:
            m.step(time.monotonic())
            await asyncio.sleep(0)
        write.assert_called_once_with(h.last_id)


if __name__ == '__main__':
    unittest.main()
