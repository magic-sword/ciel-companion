# -*- coding: utf-8 -*-
"""歌を聴く道具：声で頼まれたら、歌を聴き始める（singing.py）。
道具はすぐ戻り、返事を作り直さない。「どうぞ」の一言は、歌の係が言わせる（アプリから始めたときと同じ言い方になるように）。
聴いているあいだは会話モデルへ声を送らないので、終わりは声では頼めない（アプリの札・静けさで終える）。
使い方の決まりは config/prompts/singing_voice.md。"""
import json
import logging

from livekit.agents import RunContext, ToolResult, function_tool

log = logging.getLogger('ciel-agent.singing-tools')


@function_tool
async def start_listening_to_song(context: RunContext):
    """相手の歌を聴き始める（「歌を聴いて」「今から歌うね」「採点して」と頼まれたとき）。歌い終わったら感想を言う。"""
    song = context.userdata.song
    if song is None:
        return json.dumps({'status': 'unavailable'})
    status = song.start()
    log.info('歌の道具 status=%s', status)
    return ToolResult(json.dumps({'status': status}), reply_required=False)


TOOLS = [start_listening_to_song]
