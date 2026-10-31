# -*- coding: utf-8 -*-
"""その人について覚えていること（メモ）の道具：覚える・読む・忘れる・覚えることに同意する。
読めるのは、いま話している本人が「声を覚えている人」だと自信を持って分かったときだけ（ほかの人のメモは読めない）。
覚えるときは、会話モデルが渡した 1 文を記録係（notes.py）に預けてすぐ戻る（返事を作り直さない）。記録係が裏で今のメモと
突き合わせて保存する。記録係は、会話の流れから道具で拾い漏れたことも補う。
忘れるときも、頼まれた中身を短い言葉で記録係に預けてすぐ戻る。当てはまるメモは記録係が中身で決めて消す（番号で確かめなくてよい）。
使い方の決まりは config/prompts/speakers.md。"""
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
    await book.refresh()
    k = book.current_person()
    if k is None:
        return 'いま話している方が、声を覚えている方だと確かではないので、覚えられません。'
    if not k.notes_ok:
        return f'{k.name}さんからは、お話を覚える同意をまだもらっていません。先に同意を聞いてください。'
    # 保存は記録係（notes.py）が裏で、今のメモと突き合わせて行う。ここではすぐ戻り、返事を作り直さない
    state.notes.request(k.person_id, note)
    return ToolResult('覚えました（裏で保存します）。', reply_required=False)


@function_tool
async def forget_about_speaker(context: RunContext, what: str):
    """いま話している本人に「忘れて」「それは別の人の話」と頼まれたことを、短い言葉で渡す（例：「ルミナス王国のこと」）。
    呼ぶ前には何も言わない。結果が戻ったら、ひとことで返す。"""
    state = context.userdata
    book = state.book
    if book is None or state.notes is None:
        return NO_SPEAKERS
    await book.refresh()
    k = book.current_person()
    if k is None:
        return 'いま話している方が、声を覚えている方だと確かではないので、受け付けられません。ご本人にもう一度言ってもらってください。'
    # 当てはまるメモを消すのは記録係（notes.py）が裏で、中身で決める。シエルの気持ちからも、会話の終わりに外す（relationship.py）
    # 返事は道具のあとに作らせる（会話モデルは、先に話さずに道具だけ呼ぶことが多く、返事なしで黙ってしまうため）
    if not what.strip():
        return '忘れる内容を教えてください。'
    if book.store is not None and hasattr(book.store, 'request_forget'):
        if not await book.store.request_forget(k.person_id, what):
            return '保存されている本人情報を確認できませんでした。'
    state.notes.forget(k.person_id, what)
    # 補足情報のキャッシュから、削除前のメモや気持ちを再注入しない。
    sp = book.last
    sp.memory_suppressed = True
    sp.notes_context = ''
    sp.relation_context.clear()
    return '忘れました。この会話でも、もうその話はしない。'


@function_tool
async def agree_to_notes(context: RunContext) -> str:
    """声を覚えている本人が、お話を覚えることに同意したときに呼ぶ。"""
    book = context.userdata.book
    return await book.agree_notes() if book else NO_SPEAKERS


TOOLS = [remember_about_speaker, recall_about_speaker, forget_about_speaker, agree_to_notes]
# 配信のコメントから使ってよいか（tools/__init__.py）。どれも「いま話している本人」（声の人）のメモなので、コメントの人に当てると
# 人違いになる。読めば覚えていることを配信で知らせることにもなる
FROM_COMMENTS = {remember_about_speaker: False, recall_about_speaker: False, forget_about_speaker: False,
                 agree_to_notes: False}
