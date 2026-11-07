"""アプリの環境（app_env.py）：アプリが知らせた道具を、心が呼べる道具にする"""
import asyncio
import json
import types
import unittest
import unittest.mock

import app_env
import mind
import tools
from conversation import Conversation
from livekit.agents import llm


def packet(m, topic='ciel.app'):
    return types.SimpleNamespace(topic=topic, data=json.dumps(m, ensure_ascii=False).encode('utf-8'))


HELLO = {'v': 1, 'type': 'app.hello', 'app': 'ciel-companion', 'version': '0.9', 'tools': [
    {'name': 'app_gesture', 'description': 'シエルの体の動き', 'inputSchema': {
        'type': 'object', 'properties': {'gesture': {'type': 'string', 'enum': ['nod', 'tilt']}}, 'required': ['gesture']}},
    {'name': 'app_show_card', 'description': '画面にカード', 'inputSchema': {'type': 'object', 'properties': {}},
     '_meta': {'ciel/from_comments': True}},
    {'name': 'gesture', 'description': '名前の頭が違う', 'inputSchema': {'type': 'object'}},
    {'name': 'app_bad name', 'description': '名前に空白', 'inputSchema': {'type': 'object'}},
]}


class AppEnvTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sent = []
        self.changed = 0

        async def send(m):
            self.sent.append(m)
        self.app = app_env.AppEnv(send)
        self.app.on_tools = self.count

    def count(self):
        self.changed += 1

    async def test_hello_makes_tools_only_with_the_app_prefix(self):
        self.app.on_data(packet(HELLO, topic='ciel.other'))   # ほかの知らせでは動かない
        self.assertEqual(self.app.tools, [])
        self.app.on_data(packet(HELLO))
        self.assertEqual([t.id for t in self.app.tools], ['app_gesture', 'app_show_card'])
        self.assertEqual(self.changed, 1)
        self.app.on_data(packet(HELLO))   # 送り直しでは入れ替えない
        self.assertEqual(self.changed, 1)
        self.assertEqual(self.app.from_comments(), {'app_gesture': False, 'app_show_card': True})

    async def test_call_waits_for_the_app_result(self):
        self.app.on_data(packet(HELLO))
        task = asyncio.create_task(self.app.call('app_gesture', {'gesture': 'nod'}))
        for _ in range(50):
            if self.sent:
                break
            await asyncio.sleep(0.01)
        call = self.sent[-1]
        self.assertEqual((call['type'], call['tool'], call['args']), ('app.call', 'app_gesture', {'gesture': 'nod'}))
        self.app.on_data(packet({'v': 1, 'type': 'app.result', 'id': call['id'], 'result': {'status': 'ok'}}))
        self.assertEqual(await task, {'status': 'ok'})

    async def test_unknown_tool_and_silence(self):
        self.assertEqual(await self.app.call('app_gesture', {}), {'status': 'unavailable'})   # 知らせていない道具
        self.app.on_data(packet(HELLO))
        old = app_env.CALL_TIMEOUT
        app_env.CALL_TIMEOUT = 0.05
        try:
            self.assertEqual(await self.app.call('app_show_card', {}), {'status': 'no_answer'})
        finally:
            app_env.CALL_TIMEOUT = old

    async def test_app_tools_reach_the_mind_and_comments_only_when_allowed(self):
        self.app.on_data(packet(HELLO))
        m = mind.Mind(Conversation())
        ctx = llm.ChatContext()
        ctx.add_message(role='user', content='こんにちは')
        ids = {t.id for t in m.tools_for(ctx, tools.TOOLS + self.app.tools)}
        self.assertTrue({'app_gesture', 'app_show_card'} <= ids)
        with unittest.mock.patch.dict(tools.ENV_FROM_COMMENTS, self.app.from_comments()):
            allowed = {t.id for t in tools.for_comments(tools.TOOLS + self.app.tools)}
        self.assertIn('app_show_card', allowed)
        self.assertNotIn('app_gesture', allowed)


if __name__ == '__main__':
    unittest.main()
