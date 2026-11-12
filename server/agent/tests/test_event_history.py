"""Game facts survive speech cancellation and remain distinct from user requests."""
import json
import unittest
from types import SimpleNamespace as Obj
from unittest.mock import patch

from livekit.agents import llm
from conversation import Conversation
from mind import Mind, local_context
from mouth import Mouth


class EventHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.history = Conversation()
        self.session = Obj(userdata=Obj(history=self.history), user_state='speaking',
                           agent_state='listening', current_speech=None)
        self.mouth = Mouth(self.session)

    async def asyncTearDown(self):
        await self.mouth.reactions.close()

    async def test_interrupted_or_expired_notification_survives_next_request(self):
        h = self.history
        h.complete(h.reserve(role='user'), 'ありがとう')
        event = self.mouth.react_latest('game', instructions='シエルが倒れた', reaction_kind='died')
        self.assertNotIn('instructions', event.kwargs)
        self.mouth.reactions.finish(event, 'expired')
        h.complete(h.reserve(role='assistant'), '別の返答')
        chat = llm.ChatContext()
        chat.add_message(role='system', content='固定指示')
        brain = Mind(h)
        with patch('clock.now_line', return_value='現在'):
            messages = local_context(brain.build(chat)).items
        texts = [m.text_content or '' for m in messages]
        self.assertEqual(sum('シエルが倒れた' in text for text in texts), 1)
        self.assertLess(next(i for i,t in enumerate(texts) if 'ありがとう' in t),
                        next(i for i,t in enumerate(texts) if 'シエルが倒れた' in t))
        self.assertLess(next(i for i,t in enumerate(texts) if 'シエルが倒れた' in t), texts.index('別の返答'))
        self.assertIn('利用者の発言・依頼ではありません', next(t for t in texts if 'シエルが倒れた' in t))

    async def test_deduplication_and_occurrence_time(self):
        hub = self.mouth.reactions
        envelope = hub.envelope('game', 'game.damage', {'fact':'被ダメージ'}, event_id='damage-1')
        envelope['occurred_at'] -= 1
        hub.receive('game', envelope, why='game', kwargs={'instructions':'被ダメージ'})
        hub.receive('game', envelope, why='game', kwargs={'instructions':'被ダメージ'})
        self.assertEqual(len(self.history.turns), 1)
        record = json.loads(self.history.turns[0].text)
        self.assertEqual(record['occurred_at'], envelope['occurred_at'])
        self.assertEqual(record['source'], 'game')
        self.assertFalse(self.history.personal_lines())

    async def test_queued_fact_is_not_duplicated_as_current_instruction(self):
        self.mouth.react_latest('game', instructions='作業完了', reaction_kind='work.result')
        self.assertEqual(self.mouth.waiting(), {'game':''})
        chat = llm.ChatContext()
        chat.add_message(role='system', content='固定指示')
        chat.add_message(role='user', content='どうなった？')
        brain = Mind(self.history)
        brain.waiting = self.mouth.waiting
        with patch('clock.now_line', return_value='現在'):
            text = '\n'.join(m.text_content or '' for m in brain.build(chat).items)
        self.assertEqual(text.count('作業完了'), 1)
        self.assertEqual(brain.handed, 'game')
