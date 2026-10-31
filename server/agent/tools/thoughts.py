"""シエルの内なる考え（initiative.py）を、会話モデルが読む・預ける道具。いつ使うかは config/prompts/inner_thoughts_voice.md。"""
import json

from livekit.agents import RunContext, function_tool


@function_tool
async def read_inner_thoughts(context: RunContext) -> str:
    """シエルが心の中で今考えていること・相手について知りたいこと・話したい気持ちの満たされ具合を読む。"""
    talker = context.userdata.initiative
    if talker is None:
        return json.dumps({'status': 'unavailable'})
    return json.dumps(talker.snapshot(), ensure_ascii=False)


@function_tool
async def keep_thought(context: RunContext, text: str, kind: str = 'question') -> str:
    """あとで話したい・聞きたいことを、心の中の考えとして預ける。kindはquestion・comment・recall・researchのどれか。"""
    talker = context.userdata.initiative
    if talker is None:
        return json.dumps({'status': 'unavailable'})
    return json.dumps({'status': talker.keep(text, kind)})


TOOLS = [read_inner_thoughts, keep_thought]
# 配信のコメントから使ってよいか（tools/__init__.py）
FROM_COMMENTS = {read_inner_thoughts: True, keep_thought: True}
