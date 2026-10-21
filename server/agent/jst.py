# -*- coding: utf-8 -*-
"""日本時間。会話の記録・議事録・メモ・調べたことに書く時刻は、日本時間にそろえる。"""
from datetime import timedelta, timezone

JST = timezone(timedelta(hours=9))
