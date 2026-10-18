# -*- coding: utf-8 -*-
"""会議の議事録の道具：声で頼まれたら、とり始める・まとめる（minutes.py）。
道具はすぐ戻り、返事を作り直さない。始めた・終えたことは、議事録係の知らせ（on_change）を受けて agent.py が
シエルに一言告げさせる（アプリのボタンや管理用のコマンドから始めたときも、同じ言い方になるように）。
使い方の決まりは config/prompts/minutes_voice.md。"""
from livekit.agents import RunContext, ToolResult, function_tool
import json
import minutes as service

NO_MINUTES = '今は議事録をとれません。'


@function_tool
async def start_minutes(context: RunContext, lookback_minutes: int = 0):
    """議事録をとり始める。遅れて開始したときはlookback_minutes分前から含める（0は今から）。"""
    minutes = context.userdata.minutes
    if minutes is None:
        return NO_MINUTES
    status = minutes.start(lookback_minutes)
    if status == service.INVALID_RANGE:
        return json.dumps({'status': status})
    return ToolResult('議事録の係に伝えました。', reply_required=False)


@function_tool
async def finish_minutes(context: RunContext):
    """会議の議事録をまとめて、下書きを送る（「議事録まとめて」「議事録終わり」と頼まれたとき）。"""
    minutes = context.userdata.minutes
    if minutes is None:
        return NO_MINUTES
    minutes.finish()
    return ToolResult('議事録の係に伝えました。', reply_required=False)


@function_tool
async def summarize_past_minutes(context: RunContext, last_minutes: int = 0, first_id: int = 0, last_id: int = 0):
    """開始し忘れた会話を議事録にして送る。last_minutes=0は保持中の全会話、正数は直近の分数。
    first_id・last_idで発言の範囲も指定できる（分数と併用不可）。記録中には使わない。"""
    minutes = context.userdata.minutes
    if minutes is None:
        return NO_MINUTES
    status = minutes.summarize_past(last_minutes, first_id, last_id)
    if status in (service.PAST_QUEUED, service.PAST_PARTIAL):
        return ToolResult(json.dumps({'status': status}), reply_required=False)
    return json.dumps({'status': status, 'dropped_through': minutes.history.dropped_through})


TOOLS = [start_minutes, finish_minutes, summarize_past_minutes]
