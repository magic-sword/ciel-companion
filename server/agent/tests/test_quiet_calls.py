"""Quiet mode: Ciel replies only when called by name, or when the person it asked answers (turns.py)."""
import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
import unittest

import turns
from turns import TurnReplies
from speakers import SessionSpeaker


class QuietCallTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session = SimpleNamespace(generate_reply=lambda **k: None, agent_state='listening')
        self.book = SimpleNamespace(last=None)
        self.r = TurnReplies(self.session, self.book, None, SimpleNamespace(talk='quiet', presence='public', publish=None), '')
        self.r.encoder = object()
        self.r._reply = AsyncMock()
        self.a, self.b = SessionSpeaker(label='A'), SessionSpeaker(label='B')

    async def say(self, text, speaker=None):
        self.r._judgment_for = AsyncMock(return_value=SimpleNamespace(sp=speaker))
        self.r._texts = [text]
        self.r._reply_now()
        await asyncio.gather(*self.r._tasks)

    async def test_ai_in_a_meeting_is_not_a_call(self):
        await self.say('最近の AI の動向について話しましょう')
        await self.say('エーアイエージェントは便利だよね')
        self.r._reply.assert_not_called()
        await self.say('シエル、どう思う？')
        self.r._reply.assert_awaited_once()

    async def test_transcription_echoing_the_hint_is_ignored(self):
        self.assertTrue(turns.echoes_prompt('AIキャラクター「シエル」との会話。出てくる名前：シエル'))
        self.assertTrue(turns.echoes_prompt('出てくる名前：ハカセ'))
        self.assertFalse(turns.echoes_prompt('シエル、キャラクターの話をしよう'))

    async def test_after_a_question_only_the_person_asked_counts_as_answering(self):
        self.book.last = self.a
        self.r.on_item(SimpleNamespace(item=SimpleNamespace(role='assistant', text_content='Aさんはどう思う？')))
        await self.say('いや、それは違うと思う', speaker=self.b)   # others talking among themselves
        self.r._reply.assert_not_called()
        await self.say('うーん、賛成かな', speaker=self.a)
        self.r._reply.assert_awaited_once()

    async def test_follow_window_expires(self):
        self.book.last = self.a
        self.r.on_item(SimpleNamespace(item=SimpleNamespace(role='assistant', text_content='どう思う？')))
        self.r._asked_at = time.time() - turns.FOLLOW_SECONDS - 1
        await self.say('賛成かな', speaker=self.a)
        self.r._reply.assert_not_called()

    async def test_without_voice_identification_any_answer_counts(self):
        self.r.encoder = None
        self.book.last = self.a
        self.r.on_item(SimpleNamespace(item=SimpleNamespace(role='assistant', text_content='どう思う？')))
        await self.say('賛成かな', speaker=self.b)
        self.r._reply.assert_awaited_once()


if __name__ == '__main__':
    unittest.main()
