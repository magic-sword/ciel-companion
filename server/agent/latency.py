# -*- coding: utf-8 -*-
"""返事の速さの記録：相手の話し終わり（会話モデルの側が発言を区切った時）から、各段階までの時間をログに出す。

turns.py が start() を呼び、文字起こし・返事を頼んだ時・最初の文・最初の声などで mark() を呼ぶ。
ログの例：「返事の速さ 文字起こし +820 ms」。bench_latency.py の結果と合わせて、どこで待っているかを見る。
"""
import logging
import time

import debug_log

log = logging.getLogger('ciel-agent.latency')

_start: float | None = None
_seen: set[str] = set()


def start() -> None:
    global _start
    _start = time.time()
    _seen.clear()
    debug_log.record('turn_end')


def mark(what: str) -> None:
    """その段階を、この発言で初めて通ったときだけ記録する"""
    if _start is None or what in _seen:
        return
    _seen.add(what)
    log.info('返事の速さ %s +%.0f ms', what, (time.time() - _start) * 1000)
    debug_log.record('latency', stage=what, ms=round((time.time() - _start) * 1000))
