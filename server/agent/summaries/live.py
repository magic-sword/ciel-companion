"""会話の途中のまとめ（ライブ）を、いつ更新するか。時間ごとではなく、新しい発言の量で決める。
- 新しい発言が LIVE_TURNS 以上たまったら更新する。
- 少なくても、前の更新から LIVE_IDLE_SECONDS たっていて、新しい発言が 2 つ以上あれば更新する（ゆっくりした会話でも古くならない）。
- 更新どうしは LIVE_MIN_SECONDS 以上あける（続けて話しても、軽いモデルを呼びすぎない）。
- 「今すぐ更新」（アプリのボタン）は、新しい発言が 1 つでもあれば待たずに更新する。
静かなあいだはモデルを呼ばない。数字は実際の会話で見直す（docs/decisions/meeting-minutes-ja.md）。"""
import os

LIVE_MODEL = os.environ.get('CIEL_MINUTES_LIVE_MODEL', 'gpt-5.4-mini')
LIVE_TURNS = int(os.environ.get('CIEL_MINUTES_LIVE_TURNS', '6'))
LIVE_IDLE_SECONDS = float(os.environ.get('CIEL_MINUTES_LIVE_IDLE_SECONDS', '60'))
LIVE_MIN_SECONDS = float(os.environ.get('CIEL_MINUTES_LIVE_MIN_SECONDS', '30'))
LIVE_POLL_SECONDS = 2.0     # 新しい発言を見に行く間隔（モデルは呼ばない）
LIVE_MAX_LINES = 40         # 1 回に渡す発言の数（多ければ次の回に回す）


def due(new_turns: int, since_update: float, force: bool = False) -> bool:
    """新しい発言の数と、前の更新からの秒数で、今更新するか"""
    if new_turns <= 0:
        return False
    if force:
        return True
    if since_update < LIVE_MIN_SECONDS:
        return False
    return new_turns >= LIVE_TURNS or (new_turns >= 2 and since_update >= LIVE_IDLE_SECONDS)
