# -*- coding: utf-8 -*-
"""アプリの環境：アプリが出せる道具（画面にカードを出す・シエルの体の動き など）を、心が呼べる道具にする。
docs/game-environment-mcp-design-ja.md の 6 章。

- アプリは、つないだときと device.hello_request を受けたときに、出せる道具の一覧を送る（topic ciel.app の app.hello。
  道具の形は MCP の tools/list と同じ：name・description・inputSchema・_meta）。アプリの版ごとに出せるものが違ってよい
  （古いアプリは送らないだけ）。会話サーバーはアプリの道具の名前・中身を知らない。
- 道具の名前は app_ で始める（ほかの道具とぶつからないように）。違うものは使わない。
- 呼ばれたら app.call（id・tool・args）を送り、アプリの app.result（id・result）を待つ。アプリは名前と引数を確かめ、
  知らない道具は動かさない。答えが無ければ no_answer。
- 配信のコメントへの返事で使ってよいかは _meta の ciel/from_comments（無ければ使わない）。
- 表情・状態の表示（character.expression など）は今までどおりコードが送る。ここは、心が選んで呼ぶものだけ。
"""
import asyncio
import itertools
import json
import logging
from typing import Awaitable, Callable

log = logging.getLogger('ciel-agent.app')

TOPIC = 'ciel.app'
VERSION = 1
PREFIX = 'app_'
CALL_TIMEOUT = 5.0
MAX_TOOLS = 16


class AppEnv:
    def __init__(self, send: Callable[[dict], Awaitable[None]]) -> None:
        self.send = send                 # アプリへ送る（topic ciel.app）
        self.tools: list = []            # 心に渡す道具（LiveKit の道具に包んだもの）
        self.meta: dict[str, dict] = {}
        self.app = ''                    # アプリの名前と版（記録用）
        self.on_tools: Callable[[], None] | None = None   # 道具が変わった（agent.py が心の道具を入れ替える）
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._shown: tuple = ()

    def on_data(self, packet) -> None:
        if getattr(packet, 'topic', None) != TOPIC:
            return
        try:
            m = json.loads(packet.data.decode('utf-8'))
        except (ValueError, AttributeError, UnicodeDecodeError):
            return
        if not isinstance(m, dict):
            return
        if m.get('type') == 'app.hello':
            self._hello(m)
        elif m.get('type') == 'app.result':
            f = self._pending.pop(m.get('id'), None)
            if f is not None and not f.done():
                r = m.get('result')
                f.set_result(r if isinstance(r, dict) else {'status': 'error'})

    def _hello(self, m: dict) -> None:
        listed = m.get('tools') if isinstance(m.get('tools'), list) else []
        tools, meta = [], {}
        for t in listed[:MAX_TOOLS]:
            if not isinstance(t, dict):
                continue
            name, schema = t.get('name'), t.get('inputSchema')
            if not isinstance(name, str) or not name.startswith(PREFIX) or not name[len(PREFIX):].replace('_', '').isalnum():
                log.warning('アプリの道具の名前が決まりと違うので使わない：%r', name)
                continue
            if not isinstance(schema, dict) or schema.get('type') != 'object':
                schema = {'type': 'object', 'properties': {}}
            meta[name] = t.get('_meta') if isinstance(t.get('_meta'), dict) else {}
            tools.append((name, str(t.get('description') or ''), schema))
        shown = tuple((n, d, json.dumps(s, sort_keys=True)) for n, d, s in tools)
        self.app = f"{m.get('app') or ''} {m.get('version') or ''}".strip()
        if shown == self._shown:   # 同じ一覧（送り直し）なら入れ替えない
            return
        self._shown = shown
        self.meta = meta
        self.tools = [self._wrap(n, d, s) for n, d, s in tools]
        log.info('アプリ（%s）の道具 %d 個', self.app or '?', len(self.tools))
        if self.on_tools is not None:
            self.on_tools()

    def _wrap(self, name: str, description: str, schema: dict):
        from livekit.agents import function_tool

        async def impl(raw_arguments: dict) -> str:
            return json.dumps(await self.call(name, raw_arguments or {}), ensure_ascii=False)
        return function_tool(impl, raw_schema={'name': name, 'description': description, 'parameters': schema})

    async def call(self, name: str, args: dict) -> dict:
        """アプリの道具を呼んで、アプリの答えを待つ"""
        if name not in self.meta:
            return {'status': 'unavailable'}
        id_ = next(self._ids)
        f = asyncio.get_running_loop().create_future()
        self._pending[id_] = f
        try:
            await self.send({'v': VERSION, 'type': 'app.call', 'id': id_, 'tool': name, 'args': args})
            return await asyncio.wait_for(f, CALL_TIMEOUT)
        except asyncio.TimeoutError:
            return {'status': 'no_answer'}
        except Exception as e:
            log.info('アプリの道具 %s を呼べない：%s', name, type(e).__name__)
            return {'status': 'unavailable'}
        finally:
            self._pending.pop(id_, None)

    def from_comments(self) -> dict[str, bool]:
        return {n: bool(m.get('ciel/from_comments', False)) for n, m in self.meta.items()}
