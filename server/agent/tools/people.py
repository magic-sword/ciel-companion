# -*- coding: utf-8 -*-
"""人についての道具：話している人に名前を付ける・覚える・呼び名を直す・人違いを直す・忘れる・覚えているか調べる・この会話にいる人。
使い方の決まりは config/prompts/speakers.md。処理は speakers.SpeakerBook。"""
from livekit.agents import RunContext, function_tool

NO_SPEAKERS = '今は話している人を区別していません。'


@function_tool
async def name_speaker(context: RunContext, speaker: str, name: str, remember: bool) -> str:
    """発言者に名前を付ける。speaker は [発言者：…] に出た呼び名（例：知らない人A）。name は敬称なしの名前。
    remember は、本人が声を覚えることにはっきり同意したときだけ true。"""
    book = context.userdata.book
    return await book.name(speaker, name, remember) if book else NO_SPEAKERS


@function_tool
async def rename_speaker(context: RunContext, name: str) -> str:
    """いま話している本人の呼び名を直す（聞き間違えたとき、呼び方を変えてほしいと言われたとき）。name は新しい呼び名（敬称なし）。"""
    book = context.userdata.book
    return await book.rename(name) if book else NO_SPEAKERS


@function_tool
async def not_this_speaker(context: RunContext, name: str = '') -> str:
    """直前の発言者の判定が人違いだったとき（「私はハカセじゃない」）、その人を別の人として区別し直す。
    name は、その人の本当の名前が分かれば敬称なしで（分からなければ空）。"""
    book = context.userdata.book
    return await book.split(name) if book else NO_SPEAKERS


@function_tool
async def forget_speaker(context: RunContext, name: str) -> str:
    """本人に頼まれたときだけ、その人の声の記録を消す。name は敬称なしの名前。"""
    book = context.userdata.book
    return await book.forget(name) if book else NO_SPEAKERS


@function_tool
async def lookup_person(context: RunContext, name: str) -> str:
    """その名前の人の声を覚えているか調べる。name は敬称なしの名前。"""
    book = context.userdata.book
    return book.lookup(name) if book else NO_SPEAKERS


@function_tool
async def people_here(context: RunContext) -> str:
    """この会話で声を聞いた人（呼び名）を調べる。"""
    book = context.userdata.book
    return book.here() if book else NO_SPEAKERS


TOOLS = [name_speaker, rename_speaker, not_this_speaker, forget_speaker, lookup_person, people_here]
