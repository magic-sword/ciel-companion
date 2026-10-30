# -*- coding: utf-8 -*-
"""シエルの口：シエルを話させる入り口は、ここ 1 つにする。

それまでは、返事（turns.py）・自分から話しかける（initiative.py）・議事録の知らせ（agent.py）・歌（singing.py）・
タッチ（touch.py）・声の登録（agent.py）・あいさつが、それぞれ session.generate_reply を呼び、今話してよいかも
それぞれが決めていた（11 か所。2026-10-30）。ここに集め、なぜ話すか（why）を記録する。
- say：今すぐ話させる（相手への返事・頼まれた一言）。
- say_when_free：だれも話しておらず、シエルも考え中・話している最中でない切れ目を待ってから話させる（会議の発言に
  かぶせない）。待ちきれなければ話さない（anyway=True なら、待ったあとで話す）。
- busy：今が切れ目でないか（だれかが話している・シエルが考え中・話している）。
ログ・デバッグ用の会話ログには、なぜ話したか（why）と、その回数だけを出す（中身は debug_log の reply_request）。
"""
import asyncio
import collections
import logging
import time

import debug_log

log = logging.getLogger('ciel-agent.mouth')

WHY = ('greeting', 'reply', 'initiative', 'minutes', 'song', 'touch', 'enrolled')
FREE_POLL = 0.25


class Mouth:
    def __init__(self, session) -> None:
        self.session = session
        self.counts: collections.Counter[str] = collections.Counter()
        self.before_say = None   # 話させる直前に why を知らせる先（pipeline の心が、考える番の返事かを知る。mind.py）
        self._latest: dict[str, dict] = {}   # say_latest で、まだ言っていない最新の知らせ（why ごと）

    def busy(self) -> bool:
        s = self.session
        return (getattr(s, 'user_state', None) == 'speaking'
                or getattr(s, 'agent_state', None) in ('thinking', 'speaking', 'initializing'))

    def say(self, why: str, _latest: bool = False, **kwargs):
        """今すぐ話させる。generate_reply の返り（SpeechHandle）をそのまま返す"""
        if _latest:
            kwargs = self._latest.pop(why, kwargs)
        self.counts[why] += 1
        log.info('口：%s', why)
        debug_log.record('speak', why=why)
        if self.before_say is not None:
            self.before_say(why)
        return self.session.generate_reply(**kwargs)

    async def say_when_free(self, why: str, *, wait: float = 30.0, anyway: bool = False, settle: float = 0.0,
                            **kwargs):
        """切れ目を wait 秒まで待ってから話させる。settle 秒は続けて切れ目であること（話の途中の息つぎで言い出さない）。
        待ちきれず anyway でなければ None（呼んだ側が別の機会に回す）"""
        deadline = time.monotonic() + wait
        free_since = None
        while time.monotonic() < deadline:
            if self.busy():
                free_since = None
            elif free_since is None:
                free_since = time.monotonic()
            if free_since is not None and time.monotonic() - free_since >= settle:
                break
            await asyncio.sleep(FREE_POLL)
        if self.busy() and not anyway:
            log.info('口：%s は切れ目が来ないので話さない', why)
            return None
        return self.say(why, **kwargs)

    def say_latest(self, why: str, *, settle: float = 0.0, wait: float = 30.0, **kwargs) -> None:
        """知らせを、切れ目を待ってから言う（待ったあとは言う）。待っているあいだに同じ why の知らせが来たら、最新の 1 つだけを言う。
        長い話の途中で議事録を始めて終えたとき、「とり始めた」「まとめて送る」「送った」を話し終わりにまとめて言い、
        返事より後ろに古い知らせが続いた（2026-10-30）"""
        waiting = why in self._latest
        self._latest[why] = kwargs
        if not waiting:
            asyncio.create_task(self._say_latest(why, settle, wait))

    async def _say_latest(self, why: str, settle: float, wait: float) -> None:
        try:
            await self.say_when_free(why, wait=wait, anyway=True, settle=settle, _latest=True)
        finally:
            self._latest.pop(why, None)

    def summary(self) -> None:
        """会話の終わりに、なぜ何回話したかを出す"""
        if self.counts:
            log.info('口：この会話で話した回数 %s', dict(self.counts))
            debug_log.record('speak_summary', counts=dict(self.counts))


def of(session) -> Mouth:
    """その会話の口（agent.py が session.userdata.mouth に置く）。無ければ（試験など）その場で作る"""
    mouth = getattr(getattr(session, 'userdata', None), 'mouth', None)
    return mouth if isinstance(mouth, Mouth) else Mouth(session)
