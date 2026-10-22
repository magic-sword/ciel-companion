# -*- coding: utf-8 -*-
"""話の中断：シエルが話している途中の短い声（咳・「あっ」・相づち）では止めず、話し続けた声でだけ止める。

それまで：話し始めの判定は会話モデルの側（Realtime API の semantic_vad）。LiveKit は、その「話し始めた」
（input_speech_started）を受けた瞬間にシエルの声を止めていた。LiveKit の「0.5 秒以上で中断」「物音なら再開」は、
会話モデルの側が話し始めを判定する作りでは使われない。声の入った咳・「あっ」・「うん」でも、本当の割り込みと
同じ速さ（約 0.5 秒）で止まり、その音に返事もしていた（2026-10-22、bench_interrupt.py）。

ここでは、LiveKit が「話し始めた」を受ける処理を差し替える：
- シエルが話していないとき：今までどおり（ふつうの話し始め）。
- シエルが話しているとき：利用者の状態（話している）は今までどおり LiveKit に更新させ、声は止めさせない。
  直近 WINDOW_SECONDS 秒のマイクの声（speakers.AudioTap）が CONFIRM_SECONDS 秒たまったら、そこで止める（本当の割り込み）。
  話し始めてからの声の合計が TOTAL_SECONDS 秒になっても止める（間をあけながら長く話したとき）。
  どちらにも届かないまま話し終えたら、止めず、その発言には返事もしない（turns.py が end_of_turn で聞く）。
会話モデルの側の「話し始めたら返事を取り消す」（interrupt_response）は切る（agent.py）。止めるときは、こちらから止める。
LiveKit の中の作り（AgentActivity の _rt_session・_on_input_speech_started）が想定と違うときは差し替えず、今までどおりにする。
"""
import asyncio
import logging
import os
import time

import numpy as np

import debug_log
import speakers

log = logging.getLogger('ciel-agent.interruptions')

# シエルが話している途中で、これだけの秒数の声（LOUD_DB より大きい 20 ms の合計）がたまったら止める。0 なら差し替えない
CONFIRM_SECONDS = float(os.environ.get('CIEL_INTERRUPT_SECONDS', '0.6'))
LOUD_DB = -40.0       # 声とみなす大きさ（turns.py の LOUD_DB と同じ）
LEAD_SECONDS = 0.5    # 「話し始めた」の知らせは実際の話し始めより遅れて届くので、少し前から数える
MAX_WAIT = 15.0       # 話し終わり（end_of_turn）が来ないまま、この秒数たったら止めない（念のため）
# 声を数えるのは、直近のこの秒数だけ。本当の割り込みは続けて話すのでたまるが、間をあけた相づち（「うん。」…「うんうん。」）は
# 足し合わせない（2026-10-22、足し合わせていたら、2 秒あけた相づちで止まった）
WINDOW_SECONDS = 1.2
# 話し始めてからの声の合計がこれだけになったら止める。読点で間をあけながら長く話すと、直近の声は CONFIRM_SECONDS に
# 届かないことがある（2026-10-22、話し続けたのに止めず、その発言に返事もしなかった）。間をあけた相づちは 0.6〜0.8 秒
TOTAL_SECONDS = 1.2


def loud_seconds(audio: np.ndarray) -> float:
    n = speakers.SR // 50
    frames = audio[: len(audio) // n * n].reshape(-1, n)
    if not len(frames):
        return 0.0
    db = 20 * np.log10(np.sqrt((frames ** 2).mean(1)) + 1e-9)
    return float((db > LOUD_DB).sum()) * 0.02


def _no_interrupt(*args, **kwargs) -> asyncio.Future:
    fut = asyncio.get_running_loop().create_future()
    fut.set_result(None)
    return fut


class InterruptionGate:
    def __init__(self, session, tap: 'speakers.AudioTap', confirm_seconds: float = CONFIRM_SECONDS) -> None:
        self.session = session
        self.tap = tap
        self.confirm_seconds = confirm_seconds
        self._activity = None
        self._original = None
        self._watch: asyncio.Task | None = None
        self._start = 0.0   # 判定している声の数え始め
        self._overlap: str | None = None   # シエルが話している間の声：'pending'（判定中）・'confirmed'（止めた）・'ignored'

    def install(self) -> bool:
        """LiveKit の「話し始めた」を受ける処理を差し替える。差し替えられなければ False（今までどおり）"""
        if self.confirm_seconds <= 0:
            return False
        activity = getattr(self.session, '_activity', None)
        rt = getattr(activity, '_rt_session', None)
        original = getattr(activity, '_on_input_speech_started', None)
        if activity is None or rt is None or original is None:
            log.warning('LiveKit の中の作りが想定と違うので、中断は今までどおり（話し始めた瞬間に止める）')
            return False
        rt.off('input_speech_started', original)
        rt.on('input_speech_started', self._on_speech_started)
        self._activity, self._original = activity, original
        log.info('中断：シエルが話している途中は、声が %.1f 秒たまったら止める', self.confirm_seconds)
        return True

    def _on_speech_started(self, ev) -> None:
        if self.session.agent_state != 'speaking':
            self._original(ev)   # シエルが話していない：ふつうの話し始め
            return
        # シエルが話している：利用者の状態の更新などは LiveKit に任せ、声を止める処理だけ呼ばせない
        self._activity.interrupt = _no_interrupt
        try:
            self._original(ev)
        finally:
            del self._activity.interrupt
        if self._watch is not None and not self._watch.done():
            return   # まだ前の声を判定している
        self._overlap = 'pending'
        self._watch = asyncio.create_task(self._decide(time.time()))

    async def _decide(self, detected: float) -> None:
        start = self._start = detected - LEAD_SECONDS
        while time.time() - detected < MAX_WAIT:
            await asyncio.sleep(0.05)
            if self._overlap != 'pending':
                return   # 話し終えた（end_of_turn で決まった）
            if self.session.agent_state != 'speaking':
                self._overlap = None   # シエルが話し終えた。ふつうの発言として扱う
                return
            now = time.time()
            voiced = loud_seconds(self.tap.window(max(start, now - WINDOW_SECONDS), now))
            total = loud_seconds(self.tap.window(start, now))
            if voiced >= self.confirm_seconds or total >= TOTAL_SECONDS:
                voiced = max(voiced, total)
                self._overlap = 'confirmed'
                log.info('中断：声が %.2f 秒続いたので、シエルの話を止める', voiced)
                debug_log.record('interruption', decision='confirmed', voiced=round(voiced, 2))
                try:
                    self.session.interrupt()
                except Exception as e:   # 止められなくても会話は続ける
                    log.warning('シエルの話を止められない: %s', e)
                return
        self._ignore(loud_seconds(self.tap.window(start, time.time())))

    def _ignore(self, voiced: float) -> None:
        self._overlap = 'ignored'
        log.info('中断しない：シエルが話している間の短い声（%.2f 秒。咳・相づちなど）', voiced)
        debug_log.record('interruption', decision='ignored', voiced=round(voiced, 2))

    def end_of_turn(self) -> bool:
        """会話モデルの側が発言を区切ったときに turns.py が呼ぶ。シエルが話している間の短い声で、止めなかったものなら True
        （その発言には返事をしない）。止めた発言・ふつうの発言なら False"""
        state, self._overlap = self._overlap, None
        if state == 'pending':
            self._ignore(loud_seconds(self.tap.window(self._start, time.time())))
            if self._watch is not None:
                self._watch.cancel()
            self._overlap = None
            return True
        return state == 'ignored'
