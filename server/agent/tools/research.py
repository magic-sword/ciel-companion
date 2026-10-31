"""Web検索と、接続中の調査記録の再参照。"""
import json

from livekit.agents import RunContext, function_tool


@function_tool
async def research_web(context: RunContext, question: str) -> str:
    """Webを検索して情報を確認する。調べる対象・日付・条件が分かる質問を渡す。"""
    worker = context.userdata.researcher
    if worker is None:
        return json.dumps({'status': 'unavailable'})
    result = await worker.search(question, context.function_call.call_id, context.speech_handle)
    return json.dumps(result, ensure_ascii=False)


@function_tool
async def read_research(context: RunContext, research_id: int) -> str:
    """今の接続中に調べた記録をIDで読む。過去の調査の参照であり、最新情報の再検索ではない。"""
    history = context.userdata.history
    record = history.research.get(research_id) if history is not None else None
    if record is not None and context.userdata.researcher is not None:
        await context.userdata.researcher.notify(record)
        context.userdata.researcher.link_to_reply(record, context.speech_handle)
    return json.dumps(record.payload() if record else {'status': 'not_retained'}, ensure_ascii=False)


TOOLS = [research_web, read_research]
# 配信のコメントから使ってよいか（tools/__init__.py）
FROM_COMMENTS = {research_web: True, read_research: True}
