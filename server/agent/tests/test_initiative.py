"""Inner thoughts: think in the background, speak only when the motivation is high enough."""
import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from conversation import Conversation
import initiative
from initiative import Initiative, Thought


def make(talk='chatty', history=None):
    session = SimpleNamespace(generate_reply=Mock())
    style = SimpleNamespace(talk=talk)
    i = Initiative(session, style, 'NUDGE', history=history, instructions='THINK', correction_nudge='FIX',
                   offer_note='OFFER')
    i._agent_busy = False
    return i


def agent_finished(i, at):
    """Ciel finished speaking her reply at time `at`."""
    i._last = at
    i._agent_done_at = at


class DecisionTests(unittest.TestCase):
    def test_continues_right_after_her_reply_when_nobody_speaks(self):
        i = make()
        i.thoughts = [Thought('星空の写真を見たい', 'comment', 5.0, created=100.0)]
        agent_finished(i, 100.0)
        self.assertIsNone(i.pick(100.0 + initiative.CONTINUE_AFTER - 0.5))
        self.assertEqual(i.pick(100.0 + initiative.CONTINUE_AFTER).text, '星空の写真を見たい')
        # past the window: wait for the long-silence fallback instead
        self.assertIsNone(i.pick(100.0 + initiative.CONTINUE_WINDOW + 1))
        self.assertIsNotNone(i.pick(100.0 + initiative.FALLBACK_SECONDS))

    def test_continuation_needs_a_strong_thought_and_shares_the_cooldown(self):
        i = make()
        i.thoughts = [Thought('ふつうの考え', 'comment', 4.0, created=100.0)]
        agent_finished(i, 100.0)
        self.assertIsNone(i.pick(102.0))   # 4 waits for the next reply instead
        i.thoughts = [Thought('とても話したい', 'comment', 5.0, created=100.0)]
        i._added_at = 90.0                 # just offered one in the reply
        self.assertIsNone(i.pick(102.0))
        i._added_at = 100.0 - initiative.ADD_COOLDOWN
        self.assertIsNotNone(i.pick(102.0))

    def test_no_continuation_when_the_user_started_talking(self):
        i = make()
        i.thoughts = [Thought('星空の写真を見たい', 'comment', 5.0, created=100.0)]
        agent_finished(i, 100.0)
        i.on_user_state(SimpleNamespace(new_state='speaking'))
        i._last = 101.0
        i.on_user_state(SimpleNamespace(new_state='listening'))
        i._last = 101.0
        self.assertIsNone(i.pick(102.0))

    def test_no_continuation_after_her_own_initiative(self):
        i = make()
        i._spoke_at = 90.0   # she started this talk herself
        i.on_agent_state(SimpleNamespace(old_state='speaking', new_state='listening'))
        self.assertIsNone(i._agent_done_at)
        i._spoke_at = None
        i.on_agent_state(SimpleNamespace(old_state='speaking', new_state='listening'))
        self.assertIsNotNone(i._agent_done_at)

    def test_weak_thought_needs_long_silence(self):
        i = make()
        i.thoughts = [Thought('なんとなく', 'comment', 3.0, created=0.0)]
        i._last = 0.0
        self.assertIsNone(i.pick(20.0))
        self.assertIsNotNone(i.pick(60.0))   # +1.0 after 60 s of silence

    def test_offer_adds_one_strong_thought_with_cooldown(self):
        i = make()
        i.thoughts = [Thought('どんなカメラで撮ったのかな', 'question', 4.0), Thought('弱い', 'comment', 2.0)]
        note = i.offer()
        self.assertTrue(note.startswith('OFFER'))
        self.assertIn('[言えたら添えたいこと（相手に聞きたいこと）] どんなカメラで撮ったのかな', note)
        i.thoughts.append(Thought('次の考え', 'comment', 5.0))
        self.assertIsNone(i.offer())   # cooldown
        i._added_at -= initiative.ADD_COOLDOWN
        self.assertIn('次の考え', i.offer())
        self.assertIsNone(make('normal').offer())

    def test_old_thoughts_fade_and_unanswered_raises_the_bar(self):
        i = make()
        t = Thought('前の話', 'recall', 4.0, created=0.0)
        self.assertLess(i.score(t, initiative.STALE_SECONDS * 3), 4.0)
        i.unanswered = 2
        self.assertEqual(i.score(Thought('x', 'comment', 4.0, created=10.0), 10.0), 3.0)

    def test_normal_mode_only_urgent_corrections(self):
        i = make('normal')
        i._last = 0.0
        i.thoughts = [Thought('話したい', 'comment', 5.0, created=0.0), Thought('さっきの日付は間違い', 'correction', 5.0, created=0.0)]
        self.assertEqual(i.pick(10.0).kind, 'correction')
        i.thoughts = [Thought('少し違うかも', 'correction', 4.0, created=0.0)]
        self.assertIsNone(i.pick(10.0))

    def test_quiet_mode_never_thinks_or_speaks(self):
        i = make('quiet')
        i.thoughts = [Thought('話したい', 'comment', 5.0, created=0.0)]
        i._last = 0.0
        i.step(1000.0)
        i.session.generate_reply.assert_not_called()
        self.assertIsNone(i._thinking)

    def test_express_uses_nudge_and_counts_unanswered(self):
        i = make()
        t = Thought('冬の星空の写真を見たい', 'comment', 5.0, created=0.0)
        i._express(t, 10.0)
        self.assertIn('[話したいこと（感想）] 冬の星空の写真を見たい', i.session.generate_reply.call_args.kwargs['instructions'])
        # waiting for an answer already makes the next talk harder
        self.assertEqual(i.score(Thought('次', 'comment', 4.0, created=10.0), 10.0), 3.5)
        self.assertTrue(i.session.generate_reply.call_args.kwargs['instructions'].startswith('NUDGE'))
        self.assertTrue(t.expressed)
        i._express(Thought('もう一つ', 'comment', 5.0, created=0.0), 30.0)
        self.assertEqual(i.unanswered, 1)
        i.on_user_state(SimpleNamespace(new_state='speaking'))
        self.assertEqual(i.unanswered, 0)

    def test_correction_in_normal_mode_uses_its_own_nudge(self):
        i = make('normal')
        i._express(Thought('日付が違った', 'correction', 5.0, created=0.0), 1.0)
        self.assertTrue(i.session.generate_reply.call_args.kwargs['instructions'].startswith('FIX'))

    def test_apply_adds_rescores_drops_and_bounds(self):
        i = make()
        old = Thought('古い考え', 'comment', 3.0, created=0.0)
        keep = Thought('残す考え', 'comment', 2.0, created=0.0)
        i.thoughts = [old, keep]
        i.apply({'drop': [old.id], 'rescore': [{'id': keep.id, 'motivation': 9}],
                 'thoughts': [{'text': '新しい', 'kind': 'weird', 'motivation': 'x'},
                              {'text': '残す考え', 'kind': 'comment', 'motivation': 5},
                              {'text': '  '}, {'text': '聞きたい', 'kind': 'question', 'motivation': 4}],
                 'unknowns': ['好きな季節', 3, '']}, 1.0)
        texts = {t.text: t for t in i.thoughts}
        self.assertNotIn('古い考え', texts)
        self.assertEqual(texts['残す考え'].motivation, 5.0)
        self.assertEqual((texts['新しい'].kind, texts['新しい'].motivation), ('comment', 1.0))
        self.assertEqual(texts['聞きたい'].kind, 'question')
        self.assertEqual(i.unknowns, ['好きな季節'])
        i.apply('not a dict', 2.0)


class ThinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_turns_trigger_thinking_after_settle(self):
        h = Conversation()
        i = make(history=h)
        reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(
            {'thoughts': [{'text': '星空いいな', 'kind': 'comment', 'motivation': 4}], 'unknowns': ['住んでいる地域']})))])
        i._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=reply))))
        t = h.reserve()
        h.complete(t, '冬の星空を撮りに行ったんだ')
        i._last = 100.0                     # just talked: no idle thinking
        i.step(100.0)                       # new turn noticed
        self.assertIsNone(i._thinking)
        i.step(100.0 + initiative.THINK_SETTLE_SECONDS)
        await i._thinking
        request = json.loads(i._client.chat.completions.create.await_args.kwargs['messages'][1]['content'])
        self.assertEqual(request['conversation'][0]['text'], '冬の星空を撮りに行ったんだ')
        self.assertEqual([t.text for t in i.thoughts], ['星空いいな'])
        self.assertEqual(i.unknowns, ['住んでいる地域'])
        i.step(100.0 + initiative.THINK_SETTLE_SECONDS + 1)   # too soon to think again
        self.assertTrue(i._thinking.done())

    async def test_model_failure_keeps_conversation_going(self):
        i = make(history=Conversation())
        i._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=RuntimeError))))
        await i._think(0.0)
        self.assertEqual(i.thoughts, [])


class ReplyOfferTests(unittest.IsolatedAsyncioTestCase):
    async def test_reply_carries_the_offered_thought(self):
        from turns import TurnReplies
        session = SimpleNamespace(generate_reply=Mock())
        style = SimpleNamespace(talk='chatty', presence='close', publish=None)
        r = TurnReplies(session, None, None, style, '')
        r.initiative = SimpleNamespace(offer=lambda: 'OFFER [言えたら添えたいこと（感想）] x')
        await r._generate_reply({'instructions': '[発言者：ミナ]'})
        self.assertEqual(session.generate_reply.call_args.kwargs['instructions'],
                         '[発言者：ミナ]\n\nOFFER [言えたら添えたいこと（感想）] x')


if __name__ == '__main__':
    unittest.main()
