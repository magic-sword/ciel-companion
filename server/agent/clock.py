# -*- coding: utf-8 -*-
"""会話モデルに渡す「今」（日本時間）。会話モデルは自分では日時を知らないので、会話に書き足す。

- now_line：日付・曜日・時間帯・季節の 1 行（「[今：2026年10月25日（日）・夜・秋]」）。時間帯か日付が変わったときだけ
  会話の後ろに置く（turns.py）。会話の始めの指示に入れると、変わるたびに指示を書き換えることになり、Realtime API の
  キャッシュが効かなくなるので入れない。あいさつ（agent.py）にも添える。
- 分単位の時刻は、聞かれたときに道具 current_time で返す（tools/clock.py）。
決めたことは docs/decisions/clock-ja.md。
"""
from datetime import datetime

from jst import JST

WEEKDAYS = '月火水木金土日'
# （この時から, 呼び名）。深夜は 23 時〜4 時
BANDS = [(0, '深夜'), (5, '朝'), (10, '午前'), (12, '昼'), (16, '夕方'), (19, '夜'), (23, '深夜')]
SEASONS = {12: '冬', 1: '冬', 2: '冬', 3: '春', 4: '春', 5: '春', 6: '夏', 7: '夏', 8: '夏', 9: '秋', 10: '秋', 11: '秋'}


def band(hour: int) -> str:
    return [name for start, name in BANDS if hour >= start][-1]


def now_line(now: datetime | None = None) -> str:
    now = (now or datetime.now(JST)).astimezone(JST)
    return (f'[今：{now.year}年{now.month}月{now.day}日（{WEEKDAYS[now.weekday()]}）・{band(now.hour)}・'
            f'{SEASONS[now.month]}（日本時間）]')


def exact(now: datetime | None = None) -> dict:
    now = (now or datetime.now(JST)).astimezone(JST)
    return {'date': f'{now.year}年{now.month}月{now.day}日（{WEEKDAYS[now.weekday()]}）',
            'time': f'{now.hour}時{now.minute:02d}分', 'band': band(now.hour), 'season': SEASONS[now.month],
            'timezone': '日本時間', 'iso': now.isoformat(timespec='minutes')}
