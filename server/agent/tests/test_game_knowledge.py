"""ゲームの知識の窓口（game_knowledge.py）と、心への渡し方（mind.py の tools_for）"""
import types
import unittest
from unittest import mock

import game_knowledge
import mind
import tools as toolbox
from conversation import Conversation


def tool(name):
    return types.SimpleNamespace(id=name)


class ParseTest(unittest.TestCase):
    def test_games_are_read_from_the_setting(self):
        self.assertEqual(game_knowledge.parse('minecraft=http://127.0.0.1:8770/mcp, Other = https://x/mcp ,bad,=http://y'),
                         {'minecraft': 'http://127.0.0.1:8770/mcp', 'other': 'https://x/mcp'})
        self.assertEqual(game_knowledge.parse(''), {})

    def test_tool_belongs_to_a_game_by_its_name(self):
        with mock.patch.object(game_knowledge, 'GAMES', {'minecraft': 'http://x'}):
            self.assertEqual(game_knowledge.game_of(tool('minecraft_facts')), 'minecraft')
            self.assertIsNone(game_knowledge.game_of(tool('follow_me')))
            self.assertIsNone(game_knowledge.game_of(tool('minecraftish')))

    def test_no_setting_means_no_servers(self):
        with mock.patch.object(game_knowledge, 'GAMES', {}):
            self.assertEqual(game_knowledge.servers(), [])


class GiveTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(game_knowledge, 'GAMES', {'minecraft': 'http://x'})
        p.start()
        self.addCleanup(p.stop)

    def test_knowledge_tools_only_while_playing(self):
        body = types.SimpleNamespace(linked=True)
        m = mind.Mind(Conversation(), body=body)
        ctx = mind.llm.ChatContext()
        ctx.add_message(role='user', content='丸石は何で掘れる？')
        given = [tool('minecraft_facts'), tool('remember_about_speaker')]
        self.assertIn('minecraft_facts', [t.id for t in m.tools_for(ctx, given)])
        body.linked = False
        self.assertNotIn('minecraft_facts', [t.id for t in m.tools_for(ctx, given)])

    def test_knowledge_tools_are_allowed_from_comments(self):
        self.assertEqual([t.id for t in toolbox.for_comments([tool('minecraft_facts'), tool('unknown_tool')])],
                         ['minecraft_facts'])


if __name__ == '__main__':
    unittest.main()
