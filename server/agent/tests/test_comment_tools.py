"""配信のコメントからの返事で使う道具を分ける（tools/ の FROM_COMMENTS、mind.py の tools_for・only_given）"""
import unittest
from unittest import mock

from livekit.agents import llm

import mind
import tools
from conversation import Conversation


def ctx_with(text):
    ctx = llm.ChatContext()
    ctx.add_message(role='system', content='全部の指示')
    if text:
        ctx.add_message(role='user', content=text)
    return ctx


def chunk(*names, content=None):
    calls = [llm.FunctionToolCall(name=n, arguments='{}', call_id=f'c{i}') for i, n in enumerate(names)]
    return llm.ChatChunk(id='x', delta=llm.ChoiceDelta(role='assistant', content=content, tool_calls=calls))


class DeclarationTest(unittest.TestCase):
    def test_every_tool_is_decided(self):
        self.assertEqual(set(tools.FROM_COMMENTS), {t.id for t in tools.TOOLS})

    def test_comments_cannot_touch_people_or_minutes(self):
        allowed = {t.id for t in tools.for_comments(tools.TOOLS)}
        for name in ('forget_speaker', 'rename_speaker', 'lookup_person', 'recall_about_speaker',
                     'remember_about_speaker', 'start_minutes', 'finish_minutes', 'read_minutes'):
            self.assertNotIn(name, allowed)
        self.assertIn('research_web', allowed)
        self.assertIn('current_time', allowed)

    def test_undeclared_tools_are_not_for_comments(self):
        other = mock.Mock(id='mcp_calendar')
        self.assertEqual(tools.for_comments([other]), [])


class MindTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch('clock.now_line', return_value='[今：朝]')
        patcher.start()
        self.addCleanup(patcher.stop)
        self.mind = mind.Mind(Conversation())

    def ids(self, ctx):
        return {t.id for t in self.mind.tools_for(ctx, tools.TOOLS)}

    def test_a_comment_reply_gets_only_comment_tools(self):
        self.mind.on_say('comment')
        ctx = ctx_with(None)
        self.assertEqual(self.mind.route(ctx), 'mind')
        self.assertEqual(self.ids(ctx), {t.id for t in tools.for_comments(tools.TOOLS)})
        # 道具の結果を受けた続きも、コメントへの返事のまま
        ctx.items.append(llm.FunctionCall(call_id='c1', name='research_web', arguments='{}'))
        ctx.items.append(llm.FunctionCallOutput(call_id='c1', name='research_web', output='{}', is_error=False))
        self.assertEqual(self.mind.route(ctx), 'mind')
        self.assertNotIn('forget_speaker', self.ids(ctx))

    def test_voice_and_other_notices_get_every_tool_again(self):
        self.mind.on_say('comment')
        self.mind.route(ctx_with(None))
        self.mind.route(ctx_with('今日の天気は？'))   # 声の発言（口を通さない）
        self.assertIn('forget_speaker', self.ids(ctx_with('今日の天気は？')))
        self.mind.on_say('comment')
        self.mind.on_say('minutes')
        self.assertIn('read_minutes', self.ids(ctx_with(None)))


class OnlyGivenTest(unittest.TestCase):
    given = [mock.Mock(id='research_web')]

    def test_calls_of_tools_not_given_are_dropped(self):
        out, dropped = mind.only_given(chunk('research_web', 'forget_speaker'), self.given)
        self.assertEqual([c.name for c in out.delta.tool_calls], ['research_web'])
        self.assertEqual(dropped, ['forget_speaker'])

    def test_nothing_left_means_no_chunk(self):
        self.assertEqual(mind.only_given(chunk('start_minutes'), self.given), (None, ['start_minutes']))
        out, _ = mind.only_given(chunk('start_minutes', content='はい'), self.given)
        self.assertEqual((out.delta.content, out.delta.tool_calls), ('はい', []))

    def test_text_and_given_calls_pass_as_they_are(self):
        c = chunk('research_web')
        self.assertIs(mind.only_given(c, self.given)[0], c)
        self.assertEqual(mind.only_given('はい', self.given), ('はい', []))


if __name__ == '__main__':
    unittest.main()
