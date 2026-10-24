"""Inner thoughts: think in the background, speak only when the motivation is high enough."""
import asyncio
import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from conversation import Conversation
import initiative
from initiative import Initiative, Thought


def make(talk='chatty', history=None):
    session = SimpleNamespace(generate_reply=Mock())
    style = SimpleNamespace(talk=talk)
    i = Initiative(session, style, 'NUDGE', history=history, instructions='THINK', correction_nudge='FIX',
                   state_header='STATE')
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

    def test_state_shows_strong_thoughts_then_confirms_whether_spoken(self):
        i = make()
        camera = Thought('どんなカメラで撮ったのかな', 'question', 4.0)
        i.thoughts = [camera, Thought('弱い', 'comment', 2.0)]
        i.unknowns = ['使っているカメラ']
        note = i.state_note()
        self.assertEqual(note.split('\n'), ['STATE', 'いま気になっていること：どんなカメラで撮ったのかな（相手に聞きたいこと）',
                                              '知りたいこと：使っているカメラ', '話したい気持ち：ふつう'])
        self.assertTrue(camera.offered)
        i._state_text = note
        self.assertIsNone(i.state_note())       # unchanged: nothing to place again
        self.assertEqual(i.satiety, 0.0)        # showing alone does not sate
        i.apply({'spoken': [camera.id]}, 1.0)   # it was spoken
        self.assertNotIn(camera, i.thoughts)
        self.assertGreater(i.satiety_at(1.0), 0.9)
        self.assertIsNone(make('normal').state_note())

    def test_unused_shown_thought_stays_but_weaker(self):
        i = make()
        t = Thought('星の話', 'comment', 4.5)
        i.thoughts = [t]
        i.state_note()
        i.apply({'spoken': []}, 1.0)
        self.assertIn(t, i.thoughts)
        self.assertFalse(t.offered)
        self.assertEqual(t.motivation, 4.5 - initiative.UNUSED_OFFER_LOSS)
        self.assertEqual(i.satiety, 0.0)

    def test_sated_drive_shows_no_thoughts(self):
        i = make()
        i.thoughts = [Thought('話したい', 'comment', 5.0)]
        i.unknowns = ['好きな星座']
        i._sate(time.monotonic(), 2.0)
        note = i.state_note()
        self.assertIn('いま気になっていること：特になし', note)
        self.assertIn('満ちている', note)
        self.assertNotIn('知りたいこと', note)

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
                 'thoughts': [{'text': '新しい', 'kind': 'weird', 'motivation': 'x', 'stimulus': 's'},
                              {'text': '残す考え', 'kind': 'comment', 'motivation': 5, 'stimulus': 's'},
                              {'text': '  ', 'stimulus': 's'}, {'text': '聞きたい', 'kind': 'question', 'motivation': 4, 'stimulus': 's'}],
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
            {'thoughts': [{'text': '星空いいな', 'kind': 'comment', 'motivation': 4, 'stimulus': '冬の星空を撮った'}],
             'unknowns': ['住んでいる地域']})))])
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

    def test_state_only_shows_thoughts_fresh_to_the_current_topic(self):
        first = self.say('星空を撮りに行ったんだ。')
        old = Thought('星空、すてき', 'question', 5.0, created=0.0, anchor=0)
        self.i.thoughts = [old]
        self.say('寒かったよ。')
        self.assertIn('いま気になっていること：特になし', self.i.state_note())   # two user turns since its anchor
        fresh = Thought('寒さは大丈夫？', 'question', 4.0, anchor=first)
        self.i.thoughts.append(fresh)
        self.assertIn('寒さは大丈夫？', self.i.state_note())

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

    def test_spoken_counts_only_after_the_thought_was_shown(self):
        self.say('オリオン座が撮れたよ。')
        self.say('オリオン座、きれいなのです！', role='assistant')   # said before the thought was shown
        orion = Thought('オリオン座、きれいに撮れたのですね', 'comment', 4.0, anchor=self.h.last_id)
        self.i.thoughts = [orion]
        self.i.state_note()
        self.assertEqual(orion.shown_id, self.h.last_id)
        self.i.apply({'spoken': [orion.id]}, 1.0)
        self.assertIn(orion, self.i.thoughts)            # pending: Ciel has not spoken since it was shown
        self.assertTrue(orion.offered)
        self.assertEqual(self.i.satiety, 0.0)
        self.say('寒さは大丈夫でしたか？', role='assistant')
        self.assertEqual(self.i._ciel_since(orion.shown_id), ['寒さは大丈夫でしたか？'])
        self.i.apply({'spoken': []}, 2.0)                 # now judged on her later line: not spoken
        self.assertFalse(orion.offered)

    def test_ids_may_come_back_as_objects(self):
        t = Thought('古い', 'comment', 3.0)
        u = Thought('話した', 'comment', 3.0)
        self.i.thoughts = [t, u]
        self.i.apply({'drop': [{'id': t.id}, 5, None], 'spoken': [{'id': u.id}]}, 1.0)
        self.assertEqual(self.i.thoughts, [])

    def test_waits_while_the_user_keeps_talking(self):
        self.say('ねえ、シエル。')
        self.i._last = 100.0
        self.i._watch_history(100.0)
        self.i._last = 102.0                            # still producing speech
        self.assertFalse(self.i._should_think(100.0 + initiative.THINK_SETTLE_SECONDS))
        self.assertTrue(self.i._should_think(102.0 + initiative.THINK_SETTLE_SECONDS))


class QualityTests(unittest.IsolatedAsyncioTestCase):
    def test_no_new_thoughts_from_greetings_or_fragments(self):
        i = make()
        for content in ('greeting', 'fragment'):
            i.apply({'interpretation': {'content': content},
                     'thoughts': [{'text': 'なにを話すのかな', 'kind': 'comment', 'stimulus': '呼びかけ', 'motivation': 4}]}, 1.0)
        self.assertEqual(i.thoughts, [])
        i.apply({'interpretation': {'content': 'substantive', 'topic': '星空の撮影'},
                 'thoughts': [{'text': 'どんなカメラかな', 'kind': 'question', 'stimulus': 'オリオン座を撮った', 'motivation': 4}]}, 1.0)
        self.assertEqual([(t.text, t.topic, t.stimulus) for t in i.thoughts], [('どんなカメラかな', '星空の撮影', 'オリオン座を撮った')])

    def test_answered_thoughts_are_dropped(self):
        i = make()
        where = Thought('どこのキャンプ場かな', 'question', 4.0)
        gear = Thought('道具はどうしたのかな', 'question', 4.0)
        i.thoughts = [where, gear]
        i.apply({'answered': [where.id, {'id': gear.id}],
                 'rescore': [{'id': gear.id, 'motivation': 4}]}, 1.0, reviewed={where.id, gear.id})
        self.assertEqual(i.thoughts, [])

    def test_similar_thoughts_on_one_topic_are_capped(self):
        i = make()
        i.topic = 'AI'
        i.thoughts = [Thought(f'研究の視点{n}', 'comment', 3.0 + n / 10, topic='AI') for n in range(4)]
        i.thoughts.append(Thought('実用例を聞きたい', 'question', 4.0, topic='AI'))
        i.apply({}, 1.0)
        comments = sorted(t.text for t in i.thoughts if t.kind == 'comment')
        self.assertEqual(comments, ['研究の視点2', '研究の視点3'])
        self.assertIn('実用例を聞きたい', [t.text for t in i.thoughts])

    def test_thought_without_a_stimulus_is_not_kept(self):
        i = make()
        i.apply({'thoughts': [{'text': '今日は何を話したいのかな', 'kind': 'question', 'motivation': 4},
                              {'text': 'カメラが気になる', 'kind': 'question', 'stimulus': ' ', 'motivation': 4}]}, 1.0)
        self.assertEqual(i.thoughts, [])

    def test_topic_shift_retires_reactions_and_weakens_old_questions(self):
        i = make()
        i.topic = 'カレー'
        reaction = Thought('スパイスの香りがよさそう', 'comment', 4.0, topic='カレー')
        question = Thought('どこでスパイスを買うのかな', 'question', 4.0, topic='カレー')
        kept = Thought('辛さはどのくらいかな', 'question', 4.0, topic='カレー')
        i.thoughts = [reaction, question, kept]
        i.apply({'interpretation': {'content': 'substantive', 'topic': 'プレゼン', 'topic_shift': True},
                 'rescore': [{'id': kept.id, 'motivation': 4}]}, 1.0, reviewed={kept.id})
        self.assertNotIn(reaction, i.thoughts)
        self.assertEqual(question.motivation, 4.0 - initiative.TOPIC_SHIFT_LOSS)
        self.assertEqual(kept.motivation, 4.0)          # still relevant according to the thinker
        self.assertEqual(i.topic, 'プレゼン')

    async def test_memories_are_given_to_the_thinker_only_when_provided(self):
        h = Conversation()
        t = h.reserve()
        h.complete(t, '今朝も走ってきたよ')
        reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))])
        create = AsyncMock(return_value=reply)
        i = make(history=h)
        i._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        i.memories = lambda: ['来月フルマラソン', '  ', 3]
        await i._think(0.0)
        request = json.loads(create.await_args.kwargs['messages'][1]['content'])
        self.assertEqual(request['memories'], ['来月フルマラソン'])
        i.memories = lambda: []
        await i._think(0.0)
        self.assertNotIn('memories', json.loads(create.await_args.kwargs['messages'][1]['content']))

    def test_speaker_notes_follow_the_pushed_context(self):
        from speakers import SessionSpeaker
        sp = SessionSpeaker(label='x')
        self.assertEqual(sp.notes(), [])
        sp.notes_context = '[ハカセさんについて覚えていること（今日は2026-10-24）：来月マラソン／右膝を痛めた]'
        self.assertEqual(sp.notes(), ['来月マラソン', '右膝を痛めた'])
        sp.memory_suppressed = True
        self.assertEqual(sp.notes(), [])


class InnerStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_reply_falls_back_to_instructions_when_the_state_cannot_be_placed(self):
        from turns import TurnReplies
        session = SimpleNamespace(generate_reply=Mock())
        style = SimpleNamespace(talk='chatty', presence='close', publish=None)
        r = TurnReplies(session, None, None, style, '')
        r._clock_line = '[今]'   # 今の日時はもう置いてある（この試験では見ない）
        patcher = patch('turns.clock.now_line', return_value='[今]')
        patcher.start()
        self.addCleanup(patcher.stop)
        r.initiative = SimpleNamespace(state_note=lambda: 'STATE x', place_state=AsyncMock(return_value=False))
        await r._generate_reply({'instructions': '[発言者：ミナ]'})
        self.assertEqual(session.generate_reply.call_args.kwargs['instructions'], '[発言者：ミナ]\n\nSTATE x')
        r.initiative = SimpleNamespace(state_note=lambda: 'STATE y', place_state=AsyncMock(return_value=True))
        await r._generate_reply({'instructions': '[発言者：ミナ]'})
        self.assertEqual(session.generate_reply.call_args.kwargs['instructions'], '[発言者：ミナ]')

    async def test_state_item_is_replaced_in_place(self):
        from livekit.agents.llm import ChatContext
        ctx = ChatContext.empty()
        ctx.add_message(role='user', content='星空を撮ったよ')

        async def update(new_ctx):
            agent.chat_ctx = new_ctx
        agent = SimpleNamespace(chat_ctx=ctx, realtime_llm_session=None)
        agent.update_chat_ctx = update
        i = make()
        i.session.current_agent = agent
        self.assertTrue(await i.place_state('STATE 1'))
        await asyncio.gather(*list(i._tasks))
        self.assertTrue(await i.place_state('STATE 2'))
        await asyncio.gather(*list(i._tasks))
        texts = [item.text_content for item in agent.chat_ctx.items]
        self.assertEqual(texts, ['星空を撮ったよ', 'STATE 2'])


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
