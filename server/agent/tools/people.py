# -*- coding: utf-8 -*-
"""人についての道具：話している人に名前を付ける・覚える・呼び名を直す・人違いを直す・忘れる・覚えているか調べる・この会話にいる人。
使い方の決まりは config/prompts/speakers.md。処理は speakers.SpeakerBook。"""
from livekit.agents import RunContext, function_tool
import json
import logging

log = logging.getLogger('ciel-agent.people-tools')

NO_SPEAKERS = '今は話している人を区別していません。'


@function_tool
async def name_speaker(context: RunContext, name: str, remember: bool = False, speaker: str = '') -> str:
    """本人の自己紹介で呼ぶ。nameは敬称なし。speaker省略なら今話している本人。remember=falseは同意を待たずこの会話の呼び名だけ設定する。
    名前と声の永続保存には本人の明示同意を得てremember=true。speakerには確認済みspeaker_idも指定できる。"""
    book = context.userdata.book
    if book is None:
        return json.dumps({'status': 'unavailable', 'available': False})
    result = await book.name(speaker, name, remember)
    log.info('名前の道具 action=name status=%s speaker_id=%s', result['status'], result.get('speaker_id'))
    return json.dumps(result, ensure_ascii=False)


@function_tool
async def get_speaker_status(context: RunContext) -> str:
    """いま話している本人の名前・名前の保存状態・声の登録・同意・本人判定の確かさを確認する。名前を知らなくても呼べる。"""
    book = context.userdata.book
    if book is None:
        return json.dumps({'status': 'unavailable', 'available': False})
    result = await book.speaker_status()
    log.info('名前の道具 action=status status=%s speaker_id=%s', result['status'], result.get('speaker_id'))
    return json.dumps(result, ensure_ascii=False)


@function_tool
async def rename_speaker(context: RunContext, name: str) -> str:
    """いま話している本人の呼び名を直す（聞き間違えたとき、呼び方を変えてほしいと言われたとき）。name は新しい呼び名（敬称なし）。"""
    book = context.userdata.book
    if book is None:
        return json.dumps({'status': 'unavailable', 'available': False})
    try:
        message = await book.rename(name)
    except Exception as e:
        log.warning('名前の道具 action=rename status=failed error=%s', type(e).__name__)
        return json.dumps({'status': 'rename_failed', 'state': await book.speaker_status()}, ensure_ascii=False)
    return json.dumps({'result': message, 'state': await book.speaker_status()}, ensure_ascii=False)


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


TOOLS = [name_speaker, rename_speaker, not_this_speaker, forget_speaker, lookup_person, people_here, get_speaker_status]
