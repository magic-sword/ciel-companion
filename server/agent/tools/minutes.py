# -*- coding: utf-8 -*-
"""会議の議事録の道具：声で頼まれたら、とり始める・まとめる（minutes.py）。
道具はすぐ戻り、返事を作り直さない。始めた・終えたことは、議事録係の知らせ（on_change）を受けて agent.py が
シエルに一言告げさせる（アプリのボタンや管理用のコマンドから始めたときも、同じ言い方になるように）。
使い方の決まりは config/prompts/minutes_voice.md。"""
from livekit.agents import RunContext, ToolResult, function_tool

NO_MINUTES = '今は議事録をとれません。'


@function_tool
async def start_minutes(context: RunContext):
    """会議の議事録をとり始める（「議事録とって」と頼まれたとき）。"""
    minutes = context.userdata.minutes
    if minutes is None:
        return NO_MINUTES
    minutes.start()
    return ToolResult('議事録の係に伝えました。', reply_required=False)


@function_tool
async def finish_minutes(context: RunContext):
    """会議の議事録をまとめて、下書きを送る（「議事録まとめて」「議事録終わり」と頼まれたとき）。"""
    minutes = context.userdata.minutes
    if minutes is None:
        return NO_MINUTES
    minutes.finish()
    return ToolResult('議事録の係に伝えました。', reply_required=False)


TOOLS = [start_minutes, finish_minutes]
