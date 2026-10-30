# -*- coding: utf-8 -*-
"""会議の議事録の道具：声で頼まれたら、とり始める・まとめる（minutes.py）。
道具はすぐ戻り、返事を作り直さない。始めた・終えたことは、議事録係の知らせ（on_change）を受けて agent.py が
シエルに一言告げさせる（アプリのボタンや管理用のコマンドから始めたときも、同じ言い方になるように）。
使い方の決まりは config/prompts/minutes_voice.md。"""
from livekit.agents import RunContext, ToolResult, function_tool
import json
import logging
import minutes as service

from . import cut_preamble

NO_MINUTES = '今は議事録をとれません。'
JUST_STARTED_SECONDS = 30.0   # 始めてからこの秒数のうちの終了は、確かめてから受ける
log = logging.getLogger('ciel-agent.minutes-tools')


def result(recorder, action: str, status: str) -> dict:
    state = recorder.status()
    latest = state['latest_export']
    log.info('議事録ツール action=%s status=%s recording=%s id=%s', action, status,
             state['recording'], state['meeting_id'] or (latest['meeting_id'] if latest else None))
    return {'status': status, **state}


@function_tool
async def start_minutes(context: RunContext, lookback_minutes: int = 0, template: str = 'meeting'):
    """まとめ（議事録など）をとり始める。templateはmeeting（会議の議事録）・goals（目標と計画）・research（調べもののまとめ）。
    遅れて開始したときはlookback_minutes分前から含める（0は今から）。"""
    minutes = context.userdata.minutes
    if minutes is None:
        return NO_MINUTES
    status = minutes.start(lookback_minutes, template)
    if status in (service.INVALID_RANGE, service.UNKNOWN_TEMPLATE):
        return json.dumps({'status': status})
    cut_preamble(context)   # 「とり始めますね」を前置きのあとまで待たせない
    return ToolResult(json.dumps(result(minutes, 'start', status)), reply_required=False)


@function_tool
async def finish_minutes(context: RunContext, confirm: bool = False):
    """会議の議事録をまとめて、下書きを送る（「議事録まとめて」「議事録終わり」と頼まれたとき）。
    始めたばかりで just_started が返ったら、本当に終えるか聞いてから confirm=true で呼び直す。"""
    minutes = context.userdata.minutes
    if minutes is None:
        return NO_MINUTES
    # 始めた直後の終了は、確かめてから受ける。話の途中の頼みで始めた直後、同じ発言の「議事録開始して」を
    # 会話モデルが終了の頼みと取り違えて終わらせた（2026-10-30）
    if not confirm and minutes.recording and minutes.recording_seconds() < JUST_STARTED_SECONDS:
        return json.dumps({'status': 'just_started'})
    status = minutes.finish()
    cut_preamble(context)
    return ToolResult(json.dumps(result(minutes, 'finish', status)), reply_required=False)


@function_tool
async def get_minutes_status(context: RunContext):
    """議事録ID・記録状態・要約済み件数と、直近の作成・送信・保存・失敗結果を確認する。本文は返さない。"""
    minutes = context.userdata.minutes
    if minutes is None:
        return json.dumps({'available': False, 'recording': False})
    return json.dumps({'available': True, **result(minutes, 'status', 'ok')})


@function_tool
async def read_minutes(context: RunContext, meeting_id: str = ''):
    """議事録IDで途中要約・最近の未要約発言、または完成した下書きを読む。空なら記録中、なければ直近の議事録。送信はしない。"""
    minutes = context.userdata.minutes
    if minutes is None:
        return json.dumps({'available': False})
    data = minutes.read(meeting_id)
    log.info('議事録ツール action=read status=%s id=%s', data['status'],
             data.get('meeting_id') if data['status'] == 'ok' else None)
    return json.dumps(data, ensure_ascii=False)


@function_tool
async def summarize_past_minutes(context: RunContext, last_minutes: int = 0, first_id: int = 0, last_id: int = 0,
                                 template: str = 'meeting'):
    """開始し忘れた会話をまとめ（議事録など）にして送る。last_minutes=0は保持中の全会話、正数は直近の分数。
    first_id・last_idで発言の範囲も指定できる（分数と併用不可）。記録中には使わない。templateはstart_minutesと同じ。"""
    minutes = context.userdata.minutes
    if minutes is None:
        return NO_MINUTES
    status = minutes.summarize_past(last_minutes, first_id, last_id, template)
    data = {**result(minutes, 'summarize_past', status), 'dropped_through': minutes.history.dropped_through}
    if status in (service.PAST_QUEUED, service.PAST_PARTIAL):
        cut_preamble(context)
        return ToolResult(json.dumps(data), reply_required=False)
    return json.dumps(data)


@function_tool
async def choose_minutes_destination(context: RunContext, name: str = ''):
    """まとめ（議事録など）の送り先を切り替える（「議事録は仕事用に送って」）。nameは登録済みの送り先の名前。
    空なら今の送り先と登録済みの名前を返す。送り先の登録・削除はアプリの設定画面でだけできる。"""
    minutes = context.userdata.minutes
    if minutes is None:
        return NO_MINUTES
    data = minutes.choose_destination(name)
    log.info('議事録ツール action=destination status=%s count=%d', data['status'], len(data['destinations']))
    return json.dumps(data, ensure_ascii=False)


TOOLS = [start_minutes, finish_minutes, summarize_past_minutes, get_minutes_status, read_minutes,
         choose_minutes_destination]
