# -*- coding: utf-8 -*-
"""発言が終わったら、返事を作らせる（会話モデルの自動の返事は止めてある。agent.py の make_model）。

- 話し始め・話し終わりは、Realtime API の声の区切り（semantic_vad）が知らせる。割り込み（シエルの話を止める）も今までどおり。
- その発言の声で話者を判定し（speakers.py）、「[発言者：…]」を足してから返事を作らせる（2 人でも多人数でも）。
  2 人のときは、知らない声なら名前を聞く。多人数のときは、答えるか黙るか（[silent]）を会話モデルが決める
  （config/prompts/speakers.md、group.md）。
- 話者の識別が使えないとき（ECAPA の読み込み前・失敗、CIEL_VOICE が irodori 以外）は、すぐに返事を作らせる。
"""
import asyncio
import logging
import time

from livekit.agents import AgentSession
from livekit.agents.voice.events import UserStateChangedEvent

import speakers

log = logging.getLogger('ciel-agent.turns')


class TurnReplies:
    def __init__(self, session: AgentSession, book: speakers.SpeakerBook, tap: speakers.AudioTap) -> None:
        self.session = session
        self.book = book
        self.tap = tap
        self.encoder: speakers.Encoder | None = None
        self._started_at: float | None = None
        self._tasks: set[asyncio.Task] = set()

    async def load_encoder(self) -> None:
        """声の特徴の計算の準備（数秒かかるので、会話の始めに裏で読み込む）"""
        try:
            self.encoder = await asyncio.get_running_loop().run_in_executor(None, speakers.Encoder.get)
        except Exception:
            log.exception('ECAPA を読み込めない（話者は「不明」になる）')

    def on_user_state(self, ev: UserStateChangedEvent) -> None:
        if ev.new_state == 'speaking':
            self._started_at = ev.created_at
        elif ev.new_state == 'listening' and ev.old_state == 'speaking':
            start, self._started_at = self._started_at or ev.created_at, None
            t = asyncio.create_task(self._reply(start, ev.created_at))
            self._tasks.add(t)
            t.add_done_callback(self._tasks.discard)

    async def _reply(self, start: float, end: float) -> None:
        if self.book is None or self.encoder is None:
            self.session.generate_reply()
            return
        t0 = time.perf_counter()
        audio = speakers.voiced(self.tap.window(start - speakers.LEAD_SECONDS, end))
        seconds = len(audio) / speakers.SR
        e = None
        if self.encoder is not None and seconds >= speakers.MIN_VOICED:
            e = await asyncio.get_running_loop().run_in_executor(None, self.encoder.embed, audio)
        line = await self.book.identify(e, seconds)
        log.info('話者の判定 %.0f ms（声 %.1f 秒）', (time.perf_counter() - t0) * 1000, seconds)
        self.session.generate_reply(user_input=line)
