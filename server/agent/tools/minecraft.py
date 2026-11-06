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
async def go_to_place(context: RunContext, x: int, z: int) -> str:
    """マイクラで、座標（x, z）の場所へ歩いて行く（着いたら止まる）。"""
    body = _body(context)
    return _result(await body.do('go_to', {'x': x, 'z': z}) if body else {'status': 'unavailable'})


@function_tool
async def collect_blocks(context: RunContext, block: str, count: int) -> str:
    """マイクラで、見えている近くのブロックを掘って集める。block はブロックの英語の ID（oak_log・poppy など）か、
    呼び名（flower・log・dirt・stone・sand・coal・iron など）。count は 1〜64。"""
    body = _body(context)
    return _result(await body.do('collect', {'block': block, 'count': count}) if body else {'status': 'unavailable'})


@function_tool
async def craft_item(context: RunContext, item: str, count: int = 1) -> str:
    """マイクラで、持ち物から物を作る（oak_planks・stick・crafting_table・wooden_pickaxe など）。item は英語の ID、count は作りたい数（1〜64）。
    作業台が要る物は、近くの作業台か、持っている作業台を置いて使う。材料が足りなければ、足りない物が返る。"""
    body = _body(context)
    return _result(await body.do('craft', {'item': item, 'count': count}) if body else {'status': 'unavailable'})


@function_tool
async def give_item(context: RunContext, item: str, count: int | None = None) -> str:
    """マイクラで、持ち物を持ち主に渡す（そばへ行って投げる）。item は英語の ID（oak_log など）。count を省けば持っている分すべて。"""
    body = _body(context)
    args = {'item': item, **({'count': count} if count is not None else {})}
    return _result(await body.do('give', args) if body else {'status': 'unavailable'})


@function_tool
async def dig_down(context: RunContext, depth: int | None = None) -> str:
    """マイクラで、足元を掘って降りる。depth を省けば、木の上から地面まで。葉・原木・土・石など自然のブロックだけ掘る。"""
    body = _body(context)
    return _result(await body.do('dig_down', {'depth': depth} if depth is not None else {}) if body else {'status': 'unavailable'})


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


@function_tool
async def look_at_view(context: RunContext) -> str:
    """マイクラで、自分の目で今の景色を見る（向いている方向の 1 枚の絵。呼んだあと、その絵が見える）。"""
    body = _body(context)
    r = await body.look() if body else {'status': 'unavailable'}
    if r.get('status') == 'seen':
        r['note'] = f"景色の絵は「[わたしの目に見えている景色 #{r['view']}]」として、この続きで見える"
    return _result(r)


TOOLS = [follow_me, come_here, go_to_place, collect_blocks, craft_item, give_item, dig_down, stop_moving, look_around, look_at_view]
# 体の道具の名前（mind.py が、体とつながっていないときに外す）
BODY_TOOLS = tuple(t.id for t in TOOLS)
# 配信のコメントから使ってよいか（tools/__init__.py）。体を動かすのは持ち主だけ（docs/minecraft-design-ja.md の 6 章）
FROM_COMMENTS = {follow_me: False, come_here: False, go_to_place: False, collect_blocks: False, craft_item: False, give_item: False,
                 dig_down: False, stop_moving: False, look_around: True,
                 look_at_view: False}   # 景色の絵は 1 枚 0.3 円ほどかかるので、コメントからは見ない
