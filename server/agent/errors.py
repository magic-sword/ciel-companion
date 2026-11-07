# -*- coding: utf-8 -*-
"""エラーの係：会話サーバーのどこでエラーが起きても、1 か所で受け止めて、記録し、心とアプリに伝える。

目的の係の 1 行の誤り（呼び名を関数として呼んだ）で start_goal が内部エラーになり、心には LiveKit の「An internal error
occurred」しか返らず、アプリの表示も変わらず、ログを探して初めて分かった（2026-11-07）。
- 記録：デバッグ用の会話ログに error（どこ・例外の種類・メッセージ・自分たちのコードの場所）。会話サーバーのログにも 1 行。
- 心へ：道具のエラーは、どの道具が内部エラーになったかを返す（tool_failed）。心は正直に言い、別の道具で繰り返さない。
- アプリへ：agent.problem（kind bug、service にどこ）。接続の表示に「シエルの中でエラー」と出る。同じ所は ALERT_GAP 秒に 1 回。
- 集める：会話をまたいで数える（DATA/errors.jsonl に 1 行ずつ。取り出しは scripts/server/debug-log.sh errors）。
- メッセージに会話の中身が入ることがあるので、アプリと心には種類と場所だけ。本文は記録にだけ残す（health.py と同じ決まり）。
- 受け止める所：心の道具（wrap_tools）、裏の処理（spawn・watch）、拾い損ねた asyncio の処理（install）、体の技のエラー（report_body）。
"""
import asyncio
import functools
import json
import logging
import os
import time
import traceback
from pathlib import Path
from typing import Callable

import debug_log

log = logging.getLogger('ciel-agent.errors')

ALERT_GAP = 60.0          # 同じ所のエラーをアプリへ知らせるのは、この秒数に 1 回
MESSAGE_CHARS = 300
FRAMES = 4                # 記録する自分たちのコードの場所の数（深いほうから）
OWN = ('server/agent/', '/app/')
STORE = Path(os.environ.get('CIEL_ERRORS_FILE', str(Path(__file__).parent / 'data' / 'errors.jsonl')))
STORE_MAX_BYTES = 2_000_000


def _own_frames(exc: BaseException) -> list[str]:
    frames = traceback.extract_tb(exc.__traceback__)
    own = [f for f in frames if any(o in f.filename.replace('\\', '/') for o in OWN) and 'site-packages' not in f.filename]
    return [f'{Path(f.filename).name}:{f.lineno} {f.name}' for f in own[-FRAMES:]]


class Errors:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.notify: Callable[[dict], None] | None = None   # アプリへの知らせ（agent.py が置く）
        self.counts: dict[tuple[str, str], int] = {}
        self._alerted: dict[tuple[str, str], float] = {}
        self._clock = clock

    def report(self, where: str, exc: BaseException, *, kind: str = 'tool') -> dict:
        """エラーを受け止める。返すのは、心やアプリに渡してよい短い形（どこ・種類・場所）"""
        frames = _own_frames(exc)
        at = frames[-1] if frames else ''
        key = (where, at)
        self.counts[key] = self.counts.get(key, 0) + 1
        short = {'where': where, 'origin': kind, 'type': type(exc).__name__, 'at': at, 'count': self.counts[key]}   # origin：tool・task・body（record の kind と重ならない名前）
        message = str(exc)[:MESSAGE_CHARS]
        log.warning('エラー：%s（%s）%s %s', where, kind, type(exc).__name__, at)
        debug_log.record('error', **short, message=message, stack=frames)
        self._store({**short, 'message': message, 'stack': frames})
        now = self._clock()
        if self.notify is not None and now - self._alerted.get(key, -ALERT_GAP) >= ALERT_GAP:
            self._alerted[key] = now
            try:
                self.notify({'v': 1, 'type': 'agent.problem', 'kind': 'bug', 'service': where, 'stopped': False, 'at': at})
            except Exception:
                pass
        return short

    def report_body(self, skill: str, detail: str) -> None:
        """体（マイクラ）の技が、体の中のエラーで終わった（done の reason error）"""
        self.report(f'body.{skill}', RuntimeError(detail or 'error'), kind='body')

    def _store(self, row: dict) -> None:
        try:
            STORE.parent.mkdir(parents=True, exist_ok=True)
            if STORE.exists() and STORE.stat().st_size > STORE_MAX_BYTES:
                STORE.replace(STORE.with_suffix('.old.jsonl'))
            with STORE.open('a', encoding='utf-8') as f:
                f.write(json.dumps({'t': round(time.time(), 3), **row}, ensure_ascii=False) + '\n')
        except OSError:
            pass

    # ---- 受け止める所 ----

    def wrap_tools(self, tools: list) -> list:
        """心の道具を包む：中でエラーが起きたら記録し、心には tool_failed を返す（LiveKit の「internal error」の代わり）"""
        for t in tools:
            inner = getattr(t, '_func', None)
            if inner is None or getattr(inner, '__ciel_wrapped__', False):
                continue
            name = getattr(t, 'id', getattr(inner, '__name__', 'tool'))

            @functools.wraps(inner)
            async def guarded(*args, _inner=inner, _name=name, **kwargs):
                try:
                    return await _inner(*args, **kwargs)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    short = self.report(_name, e, kind='tool')
                    return json.dumps({"status": "tool_failed", "tool": _name, 'error': short['type'],
                                       'note': 'シエルの中の誤りで、この道具は動かなかった。同じ頼みを別の道具で繰り返さず、'
                                               'うまくいかなかったと正直に伝える'}, ensure_ascii=False)
            guarded.__ciel_wrapped__ = True
            t._func = guarded
        return tools

    def spawn(self, coro, where: str) -> asyncio.Task:
        """裏の処理を始める（終わったときにエラーなら受け止める）"""
        task = asyncio.create_task(coro)
        self.watch(task, where)
        return task

    def watch(self, task: asyncio.Task, where: str) -> asyncio.Task:
        def done(t: asyncio.Task) -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                self.report(where, exc, kind='task')
        task.add_done_callback(done)
        return task

    def install(self, loop: asyncio.AbstractEventLoop) -> None:
        """拾い損ねた asyncio の処理のエラー（だれも待っていない処理の例外）も受け止める"""
        previous = loop.get_exception_handler()

        def handler(lp, context):
            exc = context.get('exception')
            if exc is not None and not isinstance(exc, asyncio.CancelledError):
                where = getattr(context.get('task') or context.get('future'), 'get_name', lambda: 'asyncio')()
                self.report(f'task:{where}', exc, kind='task')
            if previous is not None:
                previous(lp, context)
            else:
                lp.default_exception_handler(context)
        loop.set_exception_handler(handler)


ERRORS = Errors()
