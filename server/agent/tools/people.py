# -*- coding: utf-8 -*-
"""人についての道具：話している人に名前を付ける・覚える・呼び名を直す・人違いを直す・忘れる・覚えているか調べる・この会話にいる人。
使い方の決まりは config/prompts/speakers.md。処理は speakers.SpeakerBook。"""
from livekit.agents import RunContext, function_tool
from speakers import plain_name
import json
import logging
import asyncio
import re

log = logging.getLogger('ciel-agent.people-tools')

NO_SPEAKERS = '今は話している人を区別していません。'


async def source_text(book) -> str | None:
    original = book.last
    turns = list(book.current_turns)
    pending = [t.ready.wait() for t in turns if not t.ready.is_set()]
    if pending:
        try:
            await asyncio.wait_for(asyncio.gather(*pending), 1.0)
        except asyncio.TimeoutError:
            pass
    if book.last is not original:
        return None
    return ' '.join(t.text for t in turns if t.ready.is_set())


def other_introduction(text: str, name: str) -> bool:
    target = re.escape(plain_name(name))
    return bool(re.search(rf'(?:こちら(?:の方)?は|この(?:方|人)は|あちら(?:の方)?は)\s*{target}', text)
                or re.search(rf'{target}(?:さん)?(?:の(?:名前|声).{{0,30}}覚えて|も参加|が参加)', text))


def self_claim(text: str, name: str) -> bool:
    target = re.escape(plain_name(name))
    return bool(re.search(rf'(?:^|[。！？])\s*(?:(?:シエル|しえる|AI|ＡＩ|いえ|いや|えっと|あの)[、, 　]*)*'
                          rf'(?:(?:私|わたし|僕|ぼく|俺|自分)(?:は|が|の名前は)|名前は)?'
                          rf'{target}(?:です|と申します|といいます|と言います)', text))


@function_tool
async def register_participant_name(context: RunContext, name: str, self_introduction: bool = False) -> str:
    """参加者の名前を会話中の名簿で受け付ける。他人の紹介は既定falseで声に結び付けず仮登録。本人が名乗った場合だけself_introduction=true。
    短い声・本人不明でも名前は仮受付する。永続保存や保存への同意の記録はしない。"""
    book = context.userdata.book
    if book is None:
        return json.dumps({'status': 'unavailable', 'available': False})
    text = await source_text(book)
    if text is None:
        return json.dumps({'status': 'not_current_speaker'})
    if other_introduction(text, name):
        self_introduction = False
    result = await book.register_name(name, self_introduction, confirm_identity=self_claim(text, name))
    log.info('名前の道具 action=register status=%s registration_id=%s', result['status'], result.get('registration_id'))
    return json.dumps(result, ensure_ascii=False)


@function_tool
async def confirm_participant_name(context: RunContext, registration_id: str, confirmed_name: str,
                                   remember: bool = False) -> str:
    """仮登録の名前を、いま本人が名乗った名前・声で確認する。confirmed_nameは本人が確認した名前。
    remember=trueは、その本人が名前と声と会話メモの永続保存に明示同意した場合だけ。紹介した人の同意では保存しない。"""
    book = context.userdata.book
    if book is None:
        return json.dumps({'status': 'unavailable', 'available': False})
    text = await source_text(book)
    if text is None:
        return json.dumps({'status': 'not_current_speaker'})
    if other_introduction(text, confirmed_name):
        return json.dumps({'status': 'introduced_person_must_confirm'})
    entry = book.name_registrations.get(registration_id)
    if entry is not None and entry.speaker_id is None and not self_claim(text, confirmed_name):
        return json.dumps({'status': 'pending_identity', **entry.view()})
    result = await book.confirm_name(registration_id, confirmed_name, remember)
    log.info('名前の道具 action=confirm status=%s registration_id=%s', result['status'], result.get('registration_id'))
    return json.dumps(result, ensure_ascii=False)


@function_tool
async def name_speaker(context: RunContext, name: str, remember: bool = False, speaker: str = '') -> str:
    """本人の自己紹介で呼ぶ。nameは敬称なし。speaker省略なら今話している本人。remember=falseは同意を待たずこの会話の呼び名だけ設定する。
    名前と声の永続保存には本人の明示同意を得てremember=true。speakerには確認済みspeaker_idも指定できる。"""
    book = context.userdata.book
    if book is None:
        return json.dumps({'status': 'unavailable', 'available': False})
    text = await source_text(book)
    if text is None:
        return json.dumps({'status': 'not_current_speaker'})
    if other_introduction(text, name):
        result = await book.register_name(name, False)
        return json.dumps(result, ensure_ascii=False)
    result = await book.name(speaker, name, remember)
    log.info('名前の道具 action=name status=%s speaker_id=%s', result['status'], result.get('speaker_id'))
    return json.dumps(result, ensure_ascii=False)


@function_tool
async def get_speaker_status(context: RunContext) -> str:
    """いま話している本人の名前・名前の保存状態・声の登録・同意・本人判定の確かさを確認する。名前を知らなくても呼べる。"""
    book = context.userdata.book
    if book is None:
        return json.dumps({'status': 'unavailable', 'available': False})
    await book.refresh()
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
        await book.refresh()
        message = await book.rename(name)
    except Exception as e:
        log.warning('名前の道具 action=rename status=failed error=%s', type(e).__name__)
        return json.dumps({'status': 'rename_failed', 'state': await book.speaker_status()}, ensure_ascii=False)
    return json.dumps({'result': message, 'state': await book.speaker_status()}, ensure_ascii=False)


@function_tool
async def not_this_speaker(context: RunContext, name: str = '') -> str:
    """直前の発言者の判定が人違いだったとき（「私はハカセじゃない」）、その人を別の人として区別し直す。
    本人が自分について訂正した場合だけ。他の参加者の紹介には使わない。name は本人の本当の名前（不明なら空）。"""
    book = context.userdata.book
    if book is None:
        return NO_SPEAKERS
    text = await source_text(book)
    if text is None:
        return json.dumps({'status': 'not_current_speaker'})
    # 他者紹介を本人訂正と誤解したツール呼び出しを、元発言に基づいて止める。
    negative = r'(?:^|[。！？])\s*(?:人違いです|別人です|(?:私は|わたしは|僕は|ぼくは)[^。！？]{0,40}(?:じゃない|ではない))'
    if not text or not (self_claim(text, name) if name else re.search(negative, text)):
        log.info('名前の道具 action=split status=correction_unverified')
        return json.dumps({'status': 'correction_unverified'})
    return await book.split(name)


@function_tool
async def forget_speaker(context: RunContext, name: str) -> str:
    """本人に頼まれたときだけ、その人の声の記録を消す。name は敬称なしの名前。"""
    book = context.userdata.book
    return await book.forget(name) if book else NO_SPEAKERS


@function_tool
async def lookup_person(context: RunContext, name: str) -> str:
    """その名前の人の声を覚えているか調べる。name は敬称なしの名前。"""
    book = context.userdata.book
    if book:
        await book.refresh()
    return book.lookup(name) if book else NO_SPEAKERS


@function_tool
async def people_here(context: RunContext) -> str:
    """会話中の参加者名簿を確認する。仮受付の名前・確認ID・本人との対応状態と、声を聞いた人を区別して返す。"""
    book = context.userdata.book
    if book:
        await book.refresh()
    return json.dumps(book.roster(), ensure_ascii=False) if book else NO_SPEAKERS


TOOLS = [name_speaker, rename_speaker, not_this_speaker, forget_speaker, lookup_person, people_here, get_speaker_status,
         register_participant_name, confirm_participant_name]
# 配信のコメントから使ってよいか（tools/__init__.py）。「いま話している本人」は声の人なので、コメントの人に当てると人違いになる。
# 声の記録を消す・覚えている人を知らせるのは、だれでも書けるコメントからはさせない
FROM_COMMENTS = {name_speaker: False, rename_speaker: False, not_this_speaker: False, forget_speaker: False,
                 lookup_person: False, people_here: True, get_speaker_status: False, register_participant_name: False,
                 confirm_participant_name: False}
