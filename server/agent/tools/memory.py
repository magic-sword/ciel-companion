# -*- coding: utf-8 -*-
"""その人について覚えていること（メモ）の道具：読む・忘れる・覚えることに同意する。
読めるのは、いま話している本人が「声を覚えている人」だと自信を持って分かったときだけ（ほかの人のメモは読めない）。
書くのは会話の裏の notes.py（会話モデルは書かない）。使い方の決まりは config/prompts/speakers.md。"""
from livekit.agents import RunContext, function_tool

NO_SPEAKERS = '今は話している人を区別していません。'


@function_tool
async def recall_about_speaker(context: RunContext) -> str:
    """いま話している本人について覚えていること（メモ）を読む。番号つきで返る。"""
    book = context.userdata.book
    return await book.recall() if book else NO_SPEAKERS


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


TOOLS = [recall_about_speaker, forget_about_speaker, agree_to_notes]
