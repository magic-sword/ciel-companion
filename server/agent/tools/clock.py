"""今の正確な日時（日本時間）を返す道具。日付・時間帯は会話の「[今：…]」で分かるので、分単位が要るときだけ使う（conversation.md）。"""
import json

from livekit.agents import RunContext, function_tool

import clock


@function_tool
async def current_time(context: RunContext) -> str:
    """今の正確な日付と時刻（日本時間、分まで）を調べる。"""
    return json.dumps(clock.exact(), ensure_ascii=False)


TOOLS = [current_time]
