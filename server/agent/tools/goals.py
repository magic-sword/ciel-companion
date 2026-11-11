"""Validated work requests; the game owns planning and execution."""
import json
from livekit.agents import RunContext, function_tool


@function_tool
async def submit_game_task(context: RunContext, capability: str, arguments: dict, constraints: dict,
                           title: str, seconds: int = 90) -> str:
    """ゲームの公開する能力へ作業を依頼する。引数と制約は公開schemaに従う。受付は完了ではない。"""
    runner = context.userdata.goals
    env = getattr(runner, 'env', None)
    definition = next((d for d in ((env.profile.get('work') or {}).get('capabilities', []))
                       if d['name'] == capability), {}) if env else {}
    if definition.get('preparation'):
        # The verified user item already passed the same intake. A second model
        # route cannot replace its bound coordinates or run an unresolved draft.
        intake = getattr(runner, 'intake', None)
        reply = intake._items.get(intake._current_item) if intake else None
        return json.dumps({'status': 'handled' if reply else 'clarification_required',
                           'message': reply or '施工対象を今回の発言で確定してください。'}, ensure_ascii=False)
    activity = getattr(context.userdata, 'activity', None)
    if runner and getattr(activity, 'thinking_origin', '') == 'initiative' and runner.work and runner.work['state'] != 'succeeded':
        return json.dumps({'status': 'busy', 'reason': 'awaiting_owner'})
    return json.dumps(await runner.start(capability, arguments, constraints=constraints, title=title, seconds=seconds)
                      if runner else {'status': 'unavailable'}, ensure_ascii=False)


@function_tool
async def answer_game_task(context: RunContext, decision_id: str, action: str) -> str:
    """ゲームの判断要求へ回答する。actionはretryかcancel。期限や利用者の制約を変更しない。"""
    runner = context.userdata.goals
    return json.dumps(await runner.answer(decision_id, action) if runner else {'status': 'unavailable'}, ensure_ascii=False)


@function_tool
async def stop_game_task(context: RunContext) -> str:
    """現在のゲーム作業を中止する。cancelledの確認前に止まったと断言しない。"""
    runner = context.userdata.goals
    return json.dumps(await runner.stop() if runner else {'status': 'unavailable'}, ensure_ascii=False)


@function_tool
async def game_task_status(context: RunContext) -> str:
    """現在のゲーム作業と、達成や中止の根拠を見る。"""
    runner = context.userdata.goals
    return json.dumps(runner.status() if runner else {'status': 'unavailable'}, ensure_ascii=False)


TOOLS = [submit_game_task, answer_game_task, stop_game_task, game_task_status]
GOAL_TOOLS = tuple(t.id for t in TOOLS)
FROM_COMMENTS = {submit_game_task: False, answer_game_task: False, stop_game_task: False, game_task_status: True}
