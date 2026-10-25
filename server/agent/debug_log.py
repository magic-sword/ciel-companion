# -*- coding: utf-8 -*-
"""デバッグ用の会話ログ：調べるときだけ、会話の流れを自宅サーバーのファイルに残す（ふだんは残さない）。

仕様書 8 章では利用者の音声と会話を保存しない。これはその例外で、開発・試験のときだけ入れる（2026-10-22 利用者が決めた）。
- 入れ方：環境変数 CIEL_DEBUG_LOG=1（試験用の会話サーバー）か、data/debug/ON のファイルがあるとき（本番。
  再起動しなくても、次に始まる会話から入る）。切り替えと取り出しは scripts/server/debug-log.sh。
- 残すもの：発言の文字起こし・シエルの返事の文字・返事ごとに足した 1 行（話者・議事録の状態など）・道具の呼び出しと結果・
  Unity からの知らせ・状態の変化・返事の速さ・トークン数・話者の判定の数字。音声は残さない（例外：CIEL_DEBUG_AUDIO=1 の
  試験用の会話サーバーだけ、判定に使った声を WAV で残す。save_audio）。会議につないでいるときも残す。
- 置き場所：data/debug/（自宅サーバーの中だけ。Git・デプロイ・クラウドには出さない）。会話ごとに 1 ファイル（JSON Lines）。
- CIEL_DEBUG_LOG_DAYS（既定 7）日より古いファイルは、会話が始まるたびに消す（入れていないときも消す）。

1 つの子プロセスが 1 つの会話を受け持つので、記録先はモジュールに 1 つだけ持つ（latency.py と同じ）。
"""
import json
import logging
import os
import time
from pathlib import Path

log = logging.getLogger('ciel-agent.debug_log')

DIR = Path(__file__).resolve().parent / 'data' / 'debug'
DAYS = float(os.environ.get('CIEL_DEBUG_LOG_DAYS', '7'))
TEXT_LIMIT = 8000   # 道具の結果など、1 つの値に残す文字数の上限

_path: Path | None = None


def enabled() -> bool:
    return os.environ.get('CIEL_DEBUG_LOG', '') == '1' or (DIR / 'ON').exists()


def start(room: str, **info) -> None:
    """会話の始めに呼ぶ。古いファイルを消し、入れていれば、この会話のファイルを作る"""
    global _path
    _path = None
    cleanup()
    if not enabled():
        return
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        _path = DIR / f"{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{room}.jsonl"
    except OSError:
        log.exception('デバッグ用の会話ログの置き場所を作れない')
        return
    log.info('デバッグ用の会話ログ：記録する（%s、%g 日で消す）', _path.name, DAYS)
    record('start', room=room, **info)


def record(kind: str, **data) -> None:
    """1 行を足す（入れていなければ何もしない）。書けなくても会話は止めない"""
    if _path is None:
        return
    line = {'t': round(time.time(), 3), 'kind': kind, **{k: _clip(v) for k, v in data.items()}}
    try:
        with _path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(line, ensure_ascii=False, default=str) + '\n')
    except OSError:
        log.exception('デバッグ用の会話ログを書けない')


def save_audio(name: str, pcm, sample_rate: int) -> str | None:
    """話者の判定に使った声を WAV で残す（CIEL_DEBUG_AUDIO=1 か、data/debug/AUDIO のファイルがあるときだけ。
    試験用の会話サーバーで、読み上げの声を流して調べる間だけ入れる。実際の人の声が残るので、調べ終えたら消す。本番では入れない）。
    置き場所は、この会話のログと同じ名前のフォルダー。残したファイル名を返す"""
    if _path is None or not (os.environ.get('CIEL_DEBUG_AUDIO', '') == '1' or (DIR / 'AUDIO').exists()):
        return None
    import wave
    import numpy as np
    folder = _path.with_suffix('')
    try:
        folder.mkdir(exist_ok=True)
        with wave.open(str(folder / f'{name}.wav'), 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes((np.clip(pcm, -1, 1) * 32767).astype('<i2').tobytes())
    except OSError:
        log.exception('デバッグ用の声を書けない')
        return None
    return f'{folder.name}/{name}.wav'


def cleanup() -> None:
    if not DIR.is_dir():
        return
    limit = time.time() - DAYS * 86400
    for p in [*DIR.glob('*.jsonl'), *DIR.glob('*/*.wav')]:
        try:
            if p.stat().st_mtime < limit:
                p.unlink()
        except OSError:
            pass
    for d in DIR.iterdir():
        if d.is_dir() and not any(d.iterdir()):
            try:
                d.rmdir()
            except OSError:
                pass


def _clip(v):
    if isinstance(v, str) and len(v) > TEXT_LIMIT:
        return v[:TEXT_LIMIT] + f'…（{len(v) - TEXT_LIMIT} 字省略）'
    return v


def attach(session, room, agent) -> None:
    """会話の出来事（LiveKit のイベント）を記録につなぐ。入れていなければ何もつながない。
    返事を頼むとき（generate_reply）と、会話の指示を入れ替えるとき（update_instructions）は、
    呼ぶ場所がいくつもあるので、記録してから元の処理を呼ぶものに差し替える（入れているときだけ）。"""
    if _path is None:
        return

    generate_reply = session.generate_reply

    def logged_generate_reply(*args, **kwargs):
        record('reply_request', instructions=kwargs.get('instructions'), user_input=kwargs.get('user_input'))
        return generate_reply(*args, **kwargs)

    session.generate_reply = logged_generate_reply
    update_instructions = agent.update_instructions

    async def logged_update_instructions(instructions: str):
        record('instructions_changed', chars=len(instructions))
        return await update_instructions(instructions)

    agent.update_instructions = logged_update_instructions

    def on_item(ev) -> None:
        item = ev.item
        role = getattr(item, 'role', None)
        if role is None:
            return
        metrics = {k: round(v, 3) if isinstance(v, float) else v for k, v in dict(getattr(item, 'metrics', {}) or {}).items()}
        record('item', role=role, id=item.id, text=item.text_content or '', interrupted=item.interrupted, metrics=metrics)

    def on_transcribed(ev) -> None:
        if ev.is_final:
            record('transcript', text=ev.transcript)

    def on_tools(ev) -> None:
        for call, out in zip(ev.function_calls, ev.function_call_outputs):
            record('tool', name=call.name, arguments=call.arguments, output=out.output if out else None,
                   is_error=out.is_error if out else None)

    def on_user_state(ev) -> None:
        record('user_state', old=ev.old_state, new=ev.new_state)

    def on_agent_state(ev) -> None:
        record('agent_state', old=ev.old_state, new=ev.new_state)

    def on_error(ev) -> None:
        record('error', error=repr(ev.error))

    def on_data(packet) -> None:
        try:
            payload = packet.data.decode('utf-8')
        except UnicodeDecodeError:
            payload = f'（{len(packet.data)} バイト）'
        record('data', topic=packet.topic, payload=payload)

    session.on('conversation_item_added', on_item)
    session.on('user_input_transcribed', on_transcribed)
    session.on('function_tools_executed', on_tools)
    session.on('user_state_changed', on_user_state)
    session.on('agent_state_changed', on_agent_state)
    session.on('error', on_error)
    room.on('data_received', on_data)
