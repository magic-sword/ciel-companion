"""長い目的を、目的の係（goals.py）に預ける道具。docs/goal-runner-design-ja.md の 3.1。
目的を始めるのは、持ち主の頼みでも、シエル自身の思いつきでもよい。始めた目的の段は、係が 1 つずつ進めて確かめる。
使い方は config/prompts/goals.md。"""
import json

from livekit.agents import RunContext, function_tool


def _runner(context: RunContext):
    return getattr(context.userdata, 'goals', None)


def _result(r: dict) -> str:
    return json.dumps(r, ensure_ascii=False)


@function_tool
async def start_goal(context: RunContext, title: str, make_item: str | None = None, count: int = 1, why: str = '',
                     by_myself: bool = False, first: bool = False, game: str = 'minecraft') -> str:
    """いくつもの段がある目的を始める（目的の係が、計画して 1 つずつ進め、できたかを確かめる）。
    title は見せる言葉（日本語。例「石のつるはしを作る」）。物を作る目的なら make_item に英語の ID（stone_pickaxe など）と count。
    why は目的のわけ（あれば）。by_myself は、頼まれたのではなく自分で決めた目的なら true。
    動いている目的があれば、あとでやる目的に足す。先にこちらをするなら first=true。"""
    runner = _runner(context)
    if runner is None:
        return _result({'status': 'unavailable'})
    spec = {'make': make_item, 'count': max(1, min(64, count))} if make_item else {}
    return _result(await runner.start(game, title, spec, why=why, by='ciel' if by_myself else 'owner', first=first))


@function_tool
async def add_subgoal(context: RunContext, title: str, make_item: str | None = None, count: int = 1, why: str = '') -> str:
    """目的の段が止まったとき、その原因を片づける小さな目標を作る。できたら自動で、止まった段からやり直す。
    小さな目標の中でまた止まれば、さらに小さな目標を作れる。title は見せる言葉（例「作業台を置ける広い場所へ移る」）。
    物を作る・集めるなら make_item に英語の ID と count（係が段に分ける）。無ければ自分で体の道具を使って進め、finish_step で終える。
    上の目標と同じものは作れない（輪になる）。"""
    runner = _runner(context)
    if runner is None:
        return _result({'status': 'unavailable'})
    spec = {'make': make_item, 'count': max(1, min(64, count))} if make_item else {}
    return _result(await runner.add_subgoal(title, spec, why=why))


@function_tool
async def stop_goal(context: RunContext, only_subgoal: bool = False) -> str:
    """今の目的をやめる（あとでやる目的も消す）。only_subgoal=true なら、今の小さな目標だけやめて、上の目標で止まって待つ。"""
    runner = _runner(context)
    return _result(await runner.stop(only_current=only_subgoal) if runner else {'status': 'unavailable'})


@function_tool
async def resume_goal(context: RunContext) -> str:
    """止まっている目的を、止まった段から続ける（手を変えて用意したあと・持ち主が「続けて」と言ったとき）。"""
    runner = _runner(context)
    return _result(runner.resume() if runner else {'status': 'unavailable'})


@function_tool
async def finish_step(context: RunContext, ok: bool, note: str = '') -> str:
    """目的の係に任された段（「自分で考えて進める」段）を終える。できたら ok=true、できなければ ok=false と理由。"""
    runner = _runner(context)
    return _result(runner.finish_step(ok, note) if runner else {'status': 'unavailable'})


@function_tool
async def goal_status(context: RunContext) -> str:
    """今の目的・段・直したこと・あとでやる目的を見る。"""
    runner = _runner(context)
    return _result(runner.status() if runner else {'status': 'unavailable'})


TOOLS = [start_goal, add_subgoal, stop_goal, resume_goal, finish_step, goal_status]
GOAL_TOOLS = tuple(t.id for t in TOOLS)
# 配信のコメントからは目的を動かさない（体を動かすのは持ち主とシエルだけ）。見るだけはよい
FROM_COMMENTS = {start_goal: False, add_subgoal: False, stop_goal: False, resume_goal: False, finish_step: False,
                 goal_status: True}
