"""接続中の会話の検索。永続化された人物メモにはアクセスしない。"""
import asyncio
import json
from datetime import datetime

from livekit.agents import RunContext, function_tool

from jst import JST


@function_tool
async def search_conversation(context: RunContext, query: str = '', first_id: int = 0, last_id: int = 0) -> str:
    """今の会話を短いキーワードで検索し、前後の発言も読む。空なら直近、first_id・last_id なら発言範囲。"""
    history = context.userdata.history
    if history is None:
        return json.dumps({'scope': 'current_session', 'available': False})
    result = await asyncio.to_thread(history.search, query, first_id, last_id)
    for row in result['matches']:
        row['at'] = datetime.fromtimestamp(row['at'], JST).isoformat()
    return json.dumps(result, ensure_ascii=False)


TOOLS = [search_conversation]
# 配信のコメントから使ってよいか（tools/__init__.py）。「さっき何て言った？」に答える。配信の前の会話も同じ記録にあるので、
# 配信と別の話をしたあとで同じ接続のまま配信するなら見直す
FROM_COMMENTS = {search_conversation: True}
