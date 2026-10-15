# -*- coding: utf-8 -*-
"""その人について覚えていること（メモ）の道具：覚える・読む・忘れる・覚えることに同意する。
読めるのは、いま話している本人が「声を覚えている人」だと自信を持って分かったときだけ（ほかの人のメモは読めない）。
覚えるときは、会話モデルが渡した 1 文を記録係（notes.py）に預けてすぐ戻る（返事を作り直さない）。記録係が裏で今のメモと
突き合わせて保存する。記録係は、会話の流れから道具で拾い漏れたことも補う。使い方の決まりは config/prompts/speakers.md。"""
from livekit.agents import RunContext, ToolResult, function_tool

NO_SPEAKERS = '今は話している人を区別していません。'


@function_tool
async def recall_about_speaker(context: RunContext) -> str:
    """いま話している本人について覚えていること（メモ）を読む。番号つきで返る。"""
    book = context.userdata.book
    return await book.recall() if book else NO_SPEAKERS


@function_tool
async def remember_about_speaker(context: RunContext, note: str):
    """いま話している本人について覚えておくことを、短い 1 文で渡す（「覚えて」と頼まれたとき、大事なことを聞いたとき）。
    すぐ戻るので、待たずにそのまま話してよい。"""
    state = context.userdata
    book = state.book
    if book is None or state.notes is None:
        return NO_SPEAKERS
    k = book.current_person()
    if k is None:
        return 'いま話している方が、声を覚えている方だと確かではないので、覚えられません。'
    if not k.notes_ok:
        return f'{k.name}さんからは、お話を覚える同意をまだもらっていません。先に同意を聞いてください。'
    # 保存は記録係（notes.py）が裏で、今のメモと突き合わせて行う。ここではすぐ戻り、返事を作り直さない
    state.notes.request(k.person_id, note)
    return ToolResult('覚えました（裏で保存します）。', reply_required=False)


@function_tool
async def forget_about_speaker(context: RunContext, numbers: list[int]) -> str:
    """いま話している本人に頼まれたメモを忘れる。numbers は recall_about_speaker で読んだときの番号。"""
    book = context.userdata.book
    return await book.forget_notes(numbers) if book else NO_SPEAKERS


@function_tool
async def agree_to_notes(context: RunContext) -> str:
    """声を覚えている本人が、お話を覚えることに同意したときに呼ぶ。"""
    book = context.userdata.book
    return await book.agree_notes() if book else NO_SPEAKERS


TOOLS = [remember_about_speaker, recall_about_speaker, forget_about_speaker, agree_to_notes]
