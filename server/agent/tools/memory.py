# -*- coding: utf-8 -*-
"""その人について覚えていること（メモ）の道具：覚える・読む・忘れる・覚えることに同意する。
読めるのは、いま話している本人が「声を覚えている人」だと自信を持って分かったときだけ（ほかの人のメモは読めない）。
覚えるときは、会話モデルが渡した 1 文を記録係（notes.py）に預けてすぐ戻る（返事を作り直さない）。記録係が裏で今のメモと
突き合わせて保存する。記録係は、会話の流れから道具で拾い漏れたことも補う。
忘れるときも、頼まれた中身を短い言葉で記録係に預けてすぐ戻る。当てはまるメモは記録係が中身で決めて消す（番号で確かめなくてよい）。
使い方の決まりは config/prompts/speakers.md。"""
from livekit.agents import RunContext, ToolResult, function_tool

from memory_service import MemoryService, NO_SPEAKERS


def service(context):
    return MemoryService(context.userdata.book, context.userdata.notes)


@function_tool
async def recall_about_speaker(context: RunContext) -> str:
    """いま話している本人について覚えていること（メモ）を読む。番号つきで返る。"""
    return await service(context).recall()


@function_tool
async def remember_about_speaker(context: RunContext, note: str):
    """いま話している本人について覚えておくことを、短い 1 文で渡す（「覚えて」と頼まれたとき、大事なことを聞いたとき）。
    すぐ戻るので、待たずにそのまま話してよい。"""
    result = await service(context).remember(note)
    if result['status'] == 'queued':
        return ToolResult(result, reply_required=False)
    return result


@function_tool
async def forget_about_speaker(context: RunContext, what: str):
    """いま話している本人に「忘れて」「それは別の人の話」と頼まれたことを、短い言葉で渡す（例：「ルミナス王国のこと」）。
    呼ぶ前には何も言わない。結果が戻ったら、ひとことで返す。"""
    return await service(context).forget(what)


@function_tool
async def agree_to_notes(context: RunContext) -> str:
    """声を覚えている本人が、お話を覚えることに同意したときに呼ぶ。"""
    return await service(context).agree()


TOOLS = [remember_about_speaker, recall_about_speaker, forget_about_speaker, agree_to_notes]
# 配信のコメントから使ってよいか（tools/__init__.py）。どれも「いま話している本人」（声の人）のメモなので、コメントの人に当てると
# 人違いになる。読めば覚えていることを配信で知らせることにもなる
FROM_COMMENTS = {remember_about_speaker: False, recall_about_speaker: False, forget_about_speaker: False,
                 agree_to_notes: False}
