"""TURN_CONTEXT=items: per-turn speaker lines and minutes state go into the conversation, not the instructions."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from livekit.agents import llm

from conversation import Conversation
import minutes
import turns
from turns import TurnReplies


class FakeAgent:
    def __init__(self, fail=False):
        self.chat_ctx = llm.ChatContext()
        self.updates = []
        self.fail = fail

    async def update_chat_ctx(self, ctx):
        if self.fail:
            raise RuntimeError('rejected')
        self.updates.append([m.text_content for m in ctx.items if getattr(m, 'role', None) == 'system'][-1])
        self.chat_ctx = ctx


class TurnContextTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        for target, value in [('turns.TURN_CONTEXT', 'items'), ('minutes.WEBHOOK', '')]:
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch('minutes.openai.AsyncOpenAI')
        p.start()
        self.addCleanup(p.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = patch('minutes.SAVE_DIR', Path(self.tmp.name))
        p.start()
        self.addCleanup(p.stop)
        self.m = minutes.Minutes(None, 'test', Conversation())
        self.m._write = AsyncMock()

    def replies(self, agent, parts=('[発言者：ハカセ（声を覚えている人）]', ''), presence='solo'):
        self.session = SimpleNamespace(generate_reply=Mock(), current_agent=agent)
        book = SimpleNamespace(identify_parts=AsyncMock(return_value=parts), last=None)
        r = TurnReplies(self.session, book, None, SimpleNamespace(talk='normal', presence=presence), '', minutes=self.m)
        r.encoder = object()
        r._judgment_for = AsyncMock(return_value=None)
        return r

    async def test_speaker_line_goes_after_the_utterance_not_into_instructions(self):
        agent = FakeAgent()
        r = self.replies(agent)
        await r._reply(1, 2)
        self.assertEqual(agent.updates[0], '[発言者：ハカセ（声を覚えている人）]')
        self.assertNotIn('instructions', self.session.generate_reply.call_args.kwargs)

    async def test_minutes_state_is_placed_only_when_it_changes(self):
        agent = FakeAgent()
        r = self.replies(agent)
        await r._reply(1, 2)
        await r._reply(3, 4)
        states = [u for u in agent.updates if u.startswith('[議事録状態]')]
        self.assertEqual(len(states), 1)
        self.m.start()
        await r._reply(5, 6)
        states = [u for u in agent.updates if u.startswith('[議事録状態]')]
        self.assertEqual(len(states), 2)
        self.assertTrue(json.loads(states[-1].split('[議事録状態]\n')[1])['recording'])

    async def test_person_memory_stays_in_instructions(self):
        agent = FakeAgent()
        r = self.replies(agent, parts=('[発言者：ハカセ（声を覚えている人）]', '\n[ハカセさんについて覚えていること：紅茶が好き]'))
        await r._reply(1, 2)
        self.assertIn('紅茶が好き', self.session.generate_reply.call_args.kwargs['instructions'])
        self.assertFalse(any('紅茶' in u for u in agent.updates))

    async def test_does_not_place_items_while_the_model_side_has_items_we_lack(self):
        agent = FakeAgent()
        unseen = llm.ChatContext()
        unseen.add_message(role='user', content='まだ手元に届いていない発言')
        agent.realtime_llm_session = SimpleNamespace(chat_ctx=unseen)
        r = self.replies(agent)
        await r._reply(1, 2)
        self.assertEqual(agent.updates, [])
        self.assertIn('[発言者：ハカセ（声を覚えている人）]', self.session.generate_reply.call_args.kwargs['instructions'])

    async def test_tells_the_app_when_thinking_and_when_cancelled(self):
        r = self.replies(FakeAgent())
        sent = []
        r.style.publish = sent.append
        await r._reply(1, 2)
        await r._reply(3, 4)
        self.assertEqual(sent, [{'v': 1, 'type': 'agent.thinking', 'on': True}] * 2)
        r.on_user_state(SimpleNamespace(new_state='speaking', old_state='listening', created_at=5.0))
        self.assertEqual(sent[-1], {'v': 1, 'type': 'agent.thinking', 'on': False})
        r.on_user_state(SimpleNamespace(new_state='listening', old_state='speaking', created_at=6.0))
        r.on_user_state(SimpleNamespace(new_state='speaking', old_state='listening', created_at=7.0))
        self.assertEqual(len(sent), 3)   # 知らせていないときは、取り消しを重ねて送らない

    async def test_no_reply_while_enrolling_a_voice(self):
        r = self.replies(FakeAgent())
        r.book.enrolling = object()
        await r._reply(1, 2)
        self.session.generate_reply.assert_not_called()

    async def test_falls_back_to_instructions_when_the_conversation_rejects_items(self):
        r = self.replies(FakeAgent(fail=True))
        await r._reply(1, 2)
        instructions = self.session.generate_reply.call_args.kwargs['instructions']
        self.assertIn('[発言者：ハカセ（声を覚えている人）]', instructions)
        self.assertIn('[議事録状態]', instructions)


    async def test_now_line_is_placed_only_when_the_date_or_time_band_changes(self):
        agent = FakeAgent()
        r = self.replies(agent)
        lines = iter(['[今：A・夜]', '[今：A・夜]', '[今：A・深夜]'])
        with patch('turns.clock.now_line', side_effect=lambda: next(lines)):
            for i in range(3):
                await r._reply(i * 2 + 1, i * 2 + 2)
        self.assertEqual([u for u in agent.updates if u.startswith('[今：')], ['[今：A・夜]', '[今：A・深夜]'])

    async def test_now_line_falls_back_to_instructions_and_is_retried(self):
        r = self.replies(FakeAgent(fail=True))
        await r._reply(1, 2)
        self.assertIn('[今：', self.session.generate_reply.call_args.kwargs['instructions'])
        await r._reply(3, 4)
        self.assertIn('[今：', self.session.generate_reply.call_args.kwargs['instructions'])


if __name__ == '__main__':
    unittest.main()
