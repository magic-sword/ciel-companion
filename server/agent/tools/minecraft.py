"""マイクラの体を動かす道具（minecraft.py の Body）。体とつながっていないときは、心に渡さない（mind.py の tools_for）。
使い方は config/prompts/minecraft.md。"""
import json

from livekit.agents import RunContext, function_tool


def _body(context: RunContext):
    return getattr(context.userdata, 'body', None)


def _result(r: dict) -> str:
    return json.dumps(r, ensure_ascii=False)


@function_tool
async def follow_me(context: RunContext) -> str:
    """マイクラで、持ち主についていく（止めるまで続く）。"""
    body = _body(context)
    return _result(await body.do('follow') if body else {'status': 'unavailable'})


@function_tool
async def come_here(context: RunContext) -> str:
    """マイクラで、持ち主のそばまで行く（着いたら止まる）。"""
    body = _body(context)
    return _result(await body.do('come') if body else {'status': 'unavailable'})


@function_tool
async def stop_moving(context: RunContext) -> str:
    """マイクラで、今している技（ついていく・行く・集める）をやめて、その場で待つ。"""
    body = _body(context)
    return _result(await body.stop() if body else {'status': 'unavailable'})


@function_tool
async def look_around(context: RunContext) -> str:
    """マイクラで、今の様子（体力・持ち物・時刻・近くの人と敵・していること）を見る。"""
    body = _body(context)
    text = body.context() if body else None
    return _result({'status': 'ok', 'state': text} if text else {'status': 'unavailable'})


TOOLS = [follow_me, come_here, stop_moving, look_around]
# 体の道具の名前（mind.py が、体とつながっていないときに外す）
BODY_TOOLS = tuple(t.id for t in TOOLS)
# 配信のコメントから使ってよいか（tools/__init__.py）。体を動かすのは持ち主だけ（docs/minecraft-design-ja.md の 6 章）
FROM_COMMENTS = {follow_me: False, come_here: False, stop_moving: False, look_around: True}
