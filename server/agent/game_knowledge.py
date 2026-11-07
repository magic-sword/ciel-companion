# -*- coding: utf-8 -*-
"""ゲームの知識の窓口（MCP）へつなぐ。docs/game-knowledge-design-ja.md。

- 知識はゲームの側が持つ（マイクラなら server/minecraft の minecraft-knowledge）。会話サーバーはゲームのことを知らず、
  窓口が出す道具（名前はゲームの名前で始まる。例 minecraft_facts）を、LiveKit の MCP の仕組みで受け取って心に渡すだけ。
- 窓口の場所は環境変数 CIEL_GAME_KNOWLEDGE（例 minecraft=http://127.0.0.1:8770/mcp。ゲームが増えたら , で足す）。空なら無し。
- 渡すのは、そのゲームで遊んでいる間だけ（mind.py の tools_for）。窓口の道具は読むだけなので、配信のコメントからも使ってよい。
- 窓口が止まっていても会話は続ける（LiveKit が窓口の用意に失敗しても、ほかの道具はそのまま使える）。
"""
import logging
import os

log = logging.getLogger('ciel-agent.game-knowledge')

ENV = 'CIEL_GAME_KNOWLEDGE'
TIMEOUT = 10.0   # 窓口の 1 回の答えを待つ上限（秒）


def parse(text: str) -> dict[str, str]:
    """「minecraft=http://…, other=http://…」→ {ゲーム: 窓口の場所}"""
    games = {}
    for part in (text or '').split(','):
        name, _, url = part.strip().partition('=')
        name, url = name.strip().lower(), url.strip()
        if name and url.startswith(('http://', 'https://')):
            games[name] = url
    return games


GAMES = parse(os.environ.get(ENV, ''))


def servers() -> list:
    """LiveKit の Agent に渡す MCP の窓口（mcp_servers）。部品が無ければ空"""
    if not GAMES:
        return []
    try:
        from livekit.agents.llm.mcp import MCPServerHTTP
    except ImportError as e:   # livekit-agents[mcp]（mcp パッケージ）が入っていない
        log.warning('ゲームの知識の窓口につなげない：%s', type(e).__name__)
        return []
    out = []
    for game, url in GAMES.items():
        out.append(MCPServerHTTP(url=url, transport_type='streamable_http', timeout=TIMEOUT,
                                 client_session_timeout_seconds=TIMEOUT))
        log.info('ゲームの知識の窓口：%s', game)
    return out


def game_of_name(name: str) -> str | None:
    """道具の名前が窓口の道具なら、そのゲームの名前"""
    return next((g for g in GAMES if (name or '').startswith(g + '_')), None)


def game_of(tool) -> str | None:
    """窓口の道具なら、そのゲームの名前（minecraft_facts → minecraft）。窓口の道具でなければ None"""
    name = getattr(tool, 'id', None) or ''
    return next((g for g in GAMES if name.startswith(g + '_')), None)
