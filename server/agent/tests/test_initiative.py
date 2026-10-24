"""Inner thoughts: think in the background, speak only when the motivation is high enough."""
import asyncio
import json
import time
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

    def test_continuation_needs_a_strong_thought_and_an_unsated_drive(self):
        i = make()
        i.thoughts = [Thought('ふつうの考え', 'comment', 4.0, created=100.0)]
        agent_finished(i, 100.0)
        self.assertIsNone(i.pick(102.0))   # 4 waits for the next reply instead
        i.thoughts = [Thought('とても話したい', 'comment', 5.0, created=100.0)]
        i._sate(95.0, initiative.SATE_SPEAK)   # she just spoke on her own
        self.assertIsNone(i.pick(102.0))
        i.satiety = 0.0                        # time has passed: hungry again
        self.assertIsNotNone(i.pick(102.0))

    def test_satiety_halves_over_time(self):
        i = make()
        i._sate(0.0, 2.0)
        self.assertAlmostEqual(i.satiety_at(initiative.SATIETY_HALF_LIFE), 1.0)
        i._sate(initiative.SATIETY_HALF_LIFE, 1.0)
        self.assertAlmostEqual(i.satiety_at(initiative.SATIETY_HALF_LIFE * 2), 1.0)

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

    def test_offer_then_confirm_whether_it_was_spoken(self):
        i = make()
        camera = Thought('どんなカメラで撮ったのかな', 'question', 4.0)
        i.thoughts = [camera, Thought('弱い', 'comment', 2.0)]
        note = i.offer()
        self.assertTrue(note.startswith('OFFER'))
        self.assertIn('[言えたら添えたいこと（相手に聞きたいこと）] どんなカメラで撮ったのかな', note)
        self.assertTrue(camera.offered)
        i.thoughts.append(Thought('次の考え', 'comment', 5.0))
        self.assertIsNone(i.offer())            # waits until we know whether the first was spoken
        self.assertEqual(i.satiety, 0.0)        # offering alone does not sate
        i.apply({'spoken': [camera.id]}, 1.0)   # it was spoken
        self.assertNotIn(camera, i.thoughts)
        self.assertGreater(i.satiety_at(1.0), 0.9)
        self.assertIsNone(make('normal').offer())

    def test_unused_offer_stays_but_weaker(self):
        i = make()
        t = Thought('星の話', 'comment', 4.5)
        i.thoughts = [t]
        i.offer()
        i.apply({'spoken': []}, 1.0)
        self.assertIn(t, i.thoughts)
        self.assertFalse(t.offered)
        self.assertEqual(t.motivation, 3.5)
        self.assertEqual(i.satiety, 0.0)

    def test_sated_drive_blocks_offers(self):
        i = make()
        i.thoughts = [Thought('話したい', 'comment', 4.0)]
        i._sate(time.monotonic(), 1.0)
        self.assertIsNone(i.offer())

    def test_old_thoughts_fade(self):
        i = make()
        t = Thought('前の話', 'recall', 4.0, created=0.0)
        self.assertLess(i.score(t, initiative.STALE_SECONDS * 3), 4.0)

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
        # speaking sates the drive, so the next talk is harder
        self.assertEqual(i.score(Thought('次', 'comment', 4.0, created=10.0), 10.0), 4.0 - initiative.SATE_SPEAK)
        self.assertTrue(i.session.generate_reply.call_args.kwargs['instructions'].startswith('NUDGE'))
        self.assertTrue(t.expressed)
        i._express(Thought('もう一つ', 'comment', 5.0, created=0.0), 30.0)
        self.assertEqual(i.unanswered, 1)
        # unanswered talk adds embarrassment on top
        self.assertGreater(i.satiety_at(30.0), initiative.SATE_SPEAK * 1.5)
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


class StalenessTests(unittest.TestCase):
    def setUp(self):
        self.h = Conversation()
        self.i = make(history=self.h)

    def say(self, text, role='user'):
        t = self.h.reserve(role=role)
        self.h.complete(t, text)
        return t.id

    def test_reaction_expires_after_the_conversation_moves_on(self):
        first = self.say('ねえ、シエル。')
        called = Thought('呼ばれたのです、何か用かな？', 'comment', 4.0, created=0.0, anchor=first)
        wish = Thought('使っているカメラを知りたい', 'question', 4.0, created=0.0, anchor=first)
        self.i.thoughts = [called, wish]
        self.say('はい、なんでしょう？', role='assistant')
        self.say('昨日、星空を撮りに行ったんだ。')
        self.assertTrue(self.i.alive(called, 1.0))     # one user turn later: still alive
        self.say('オリオン座がきれいだった。')
        self.assertFalse(self.i.alive(called, 1.0))    # two user turns later: done
        self.assertTrue(self.i.alive(wish, 1.0))       # questions from unknowns live on

    def test_offer_only_thoughts_fresh_to_the_current_topic(self):
        first = self.say('星空を撮りに行ったんだ。')
        old = Thought('星空、すてき', 'question', 5.0, created=0.0, anchor=0)
        self.i.thoughts = [old]
        self.say('寒かったよ。')
        self.assertIsNone(self.i.offer())              # two user turns since its anchor
        fresh = Thought('寒さは大丈夫？', 'question', 4.0, anchor=first)
        self.i.thoughts.append(fresh)
        self.assertIn('寒さは大丈夫？', self.i.offer())

    def test_unreviewed_thoughts_sink_and_reviewed_ones_reanchor(self):
        kept = Thought('流れ星の話を聞きたい', 'question', 4.0)
        ignored = Thought('なんとなく', 'comment', 4.0)
        self.i.thoughts = [kept, ignored]
        self.i._seen_id = 7
        self.i.apply({'rescore': [{'id': kept.id, 'motivation': 4}]}, 1.0, reviewed={kept.id, ignored.id})
        self.assertEqual(kept.motivation, 4.0)
        self.assertEqual(kept.anchor, 7)
        self.assertEqual(ignored.motivation, 3.0)

    def test_fragments_of_one_speaker_are_joined_for_the_thinker(self):
        self.say('オリオン座がきれいに撮れたよ。')
        self.say('でも、')
        self.say('寒くて手がかじかんじゃった。')
        self.say('大変でしたね。', role='assistant')
        lines = self.i._conversation()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]['text'], 'オリオン座がきれいに撮れたよ。でも、寒くて手がかじかんじゃった。')
        self.assertEqual(lines[1]['speaker'], 'シエル')

    def test_waits_while_the_user_keeps_talking(self):
        self.say('ねえ、シエル。')
        self.i._last = 100.0
        self.i._watch_history(100.0)
        self.i._last = 102.0                            # still producing speech
        self.assertFalse(self.i._should_think(100.0 + initiative.THINK_SETTLE_SECONDS))
        self.assertTrue(self.i._should_think(102.0 + initiative.THINK_SETTLE_SECONDS))


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



class ToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_read_and_keep_thoughts(self):
        from tools.thoughts import keep_thought, read_inner_thoughts
        i = make()
        i.thoughts = [Thought('星空の写真を見たい', 'comment', 5.0)]
        i.unknowns = ['使っているカメラ']
        ctx = SimpleNamespace(userdata=SimpleNamespace(initiative=i))
        data = json.loads(await read_inner_thoughts(ctx))
        self.assertEqual(data['thoughts'][0], {'text': '星空の写真を見たい', 'kind': '感想', 'want': 'とても話したい'})
        self.assertEqual(data['unknowns'], ['使っているカメラ'])
        self.assertEqual(data['talk_drive'], 'ふつう')
        self.assertNotIn('motivation', json.dumps(data))
        self.assertEqual(json.loads(await keep_thought(ctx, 'あとで流れ星の話を聞きたい'))['status'], 'kept')
        self.assertEqual(json.loads(await keep_thought(ctx, 'あとで流れ星の話を聞きたい'))['status'], 'already_kept')
        self.assertEqual(i.thoughts[-1].kind, 'question')
        none = SimpleNamespace(userdata=SimpleNamespace(initiative=None))
        self.assertEqual(json.loads(await read_inner_thoughts(none))['status'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
