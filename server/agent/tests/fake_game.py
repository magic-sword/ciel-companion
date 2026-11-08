"""試験用の小さなゲーム（MCP のサーバー）。マイクラを使わずに、会話サーバーがゲームを知らずに動くかを確かめる。
「シエルのゲームの決まり」（版 1。docs/game-environment-mcp-design-ja.md の 4 章）だけを守る、作り物のゲーム「テスト」。"""
import base64
import contextlib
import json

import anyio
from mcp import ClientSession, types
from mcp.server.lowlevel import Server
from mcp.shared.memory import create_client_server_memory_streams

JPEG = b'\xff\xd8\xff\xe0' + b'0' * 64

PROFILE = {
    'profile': 1, 'game': 'test', 'label': 'テスト',
    'route_words': '跳んで|拾って',
    'link_tool': 'test_link', 'stop_tool': 'test_stop',
    'goals': {'plan': 'test_goal_plan', 'step': 'test_goal_step', 'repair': 'test_goal_repair'},
    'goal_triggers': {'start_goal': ['宝箱を作っておいて']},
    'talker_examples': ['えらいね'],
    'reasons': {'stopped': '止められた', 'no_key': '鍵が無い', 'error': 'うまくいかなかった'},
    'quiet_reasons': ['stopped'],
}
EMPTY = {'type': 'object', 'properties': {}}
TOOLS = [
    types.Tool(name='test_jump', description='跳ぶ', inputSchema={'type': 'object', 'properties': {'height': {'type': 'integer'}}},
               _meta={'ciel/role': 'act', 'ciel/long_running': True, 'ciel/from_comments': False,
                      'ciel/triggers': ['ちょっと跳んでみて']}),
    types.Tool(name='test_stop', description='止まる', inputSchema=EMPTY, _meta={'ciel/role': 'act', 'ciel/stops': True}),
    types.Tool(name='test_look', description='見る', inputSchema=EMPTY, _meta={'ciel/role': 'look', 'ciel/triggers': ['何が見える？']}),
    types.Tool(name='test_facts', description='調べる', inputSchema=EMPTY,
               _meta={'ciel/role': 'know', 'ciel/from_comments': True}),
    types.Tool(name='test_link', description='受け持つ', inputSchema={'type': 'object', 'properties': {'on': {'type': 'boolean'}}},
               _meta={'ciel/role': 'link'}),
    types.Tool(name='test_goal_plan', description='計画', inputSchema={'type': 'object', 'properties': {'spec': {'type': 'object'}}},
               _meta={'ciel/role': 'goal'}),
    types.Tool(name='test_goal_step', description='段', inputSchema={'type': 'object', 'properties': {'step': {'type': 'object'}}},
               _meta={'ciel/role': 'goal'}),
    types.Tool(name='test_goal_repair', description='直す', inputSchema={'type': 'object', 'properties': {}},
               _meta={'ciel/role': 'goal'}),
    types.Tool(name='other_thing', description='名前の頭が違う', inputSchema=EMPTY, _meta={'ciel/role': 'act'}),
]


class FakeGame:
    def __init__(self):
        self.server = Server('fake-game')
        self.busy = False          # ほかの会話が体を使っている
        self.linked = False
        self.calls: list[tuple[str, dict]] = []
        self.steps: list[dict] = []        # 段の結果（goal_step が順に返す）
        self.repairs: list[dict] = []      # 直し方（goal_repair が順に返す）
        self.plan = {'steps': [{'kind': 'make', 'args': {'item': 'chest'}, 'label': '宝箱を作る', 'progress': None}]}
        self.state = {'label': 'テスト', 'linked': True, 'playing': True, 'reason': '', 'text': 'シエル：元気', 'fingerprint': 'a'}
        self.state['body'] = {'version': 1, 'session': 'test', 'epoch': 'test', 'revision': 0, 'current': None, 'pending': None, 'last': None}
        self.session = None
        self._register()

    def _register(self):
        s = self.server

        @s.list_tools()
        async def list_tools():
            return TOOLS

        @s.call_tool(validate_input=False)
        async def call_tool(name, arguments):
            self.session = s.request_context.session
            self.calls.append((name, arguments))
            return self.answer(name, arguments)

        @s.list_resources()
        async def list_resources():
            return [types.Resource(uri='game://state', name='state'), types.Resource(uri='game://profile', name='profile')]

        @s.read_resource()
        async def read_resource(uri):
            return json.dumps(PROFILE if str(uri) == 'game://profile' else self.state, ensure_ascii=False)

        @s.list_prompts()
        async def list_prompts():
            return [types.Prompt(name='play')]

        @s.get_prompt()
        async def get_prompt(name, arguments):
            return types.GetPromptResult(messages=[types.PromptMessage(
                role='user', content=types.TextContent(type='text', text='テストの遊び方：跳ぶときは test_jump。'))])

    def answer(self, name, a):
        text = lambda r: [types.TextContent(type='text', text=json.dumps(r, ensure_ascii=False))]   # noqa: E731
        if name == 'test_link':
            if not a.get('on'):
                self.linked = False
                return text({'status': 'off'})
            self.linked = not self.busy
            return text({'status': 'linked' if self.linked else 'busy'})
        if name == 'test_jump':
            return text({'status': 'started', 'task': 7, 'title': f"{a.get('height', 1)} だけ跳ぶ"})
        if name == 'test_stop':
            return text({'status': 'stopped'})
        if name == 'test_look':
            return [types.ImageContent(type='image', data=base64.b64encode(JPEG).decode(), mimeType='image/jpeg'),
                    *text({'status': 'seen', 'note': '北を向いている'})]
        if name == 'test_facts':
            return text({'status': 'ok', 'fact': '宝箱は板 8 枚'})
        if name == 'test_goal_plan':
            return text(self.plan)
        if name == 'test_goal_step':
            return text(self.steps.pop(0))
        if name == 'test_goal_repair':
            return text(self.repairs.pop(0) if self.repairs else {'steps': None})
        return text({'status': 'error'})

    async def emit(self, event: dict):
        """出来事の知らせ（notifications/message、logger ciel.event）"""
        await self.session.send_log_message(level='info', data=event, logger='ciel.event')

    async def changed(self, **state):
        self.state.update(state)
        await self.session.send_resource_updated('game://state')

    @contextlib.asynccontextmanager
    async def connect(self, env):
        """GameEnv の connect に渡す：手元のメモリーの上で、このゲームへつなぐ"""
        async with create_client_server_memory_streams() as (client, server):
            async with anyio.create_task_group() as tg:
                tg.start_soon(lambda: self.server.run(server[0], server[1], self.server.create_initialization_options()))
                try:
                    async with ClientSession(client[0], client[1], logging_callback=env._on_log,
                                             message_handler=env._on_message) as session:
                        yield session
                finally:
                    tg.cancel_scope.cancel()
