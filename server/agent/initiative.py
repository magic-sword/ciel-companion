# -*- coding: utf-8 -*-
"""おしゃべり度が「おしゃべり」のとき（mode.py）、しばらく静かなら、シエルから話しかける。

- 人もシエルも話していない時間が FIRST_SECONDS 続いたら、「[自分から話しかける]」の合図
  （config/prompts/talk_chatty_nudge.md）を添えて返事を作らせる。話題の選び方は talk_chatty.md。
- 話しかけても人が話さなければ、次に話しかけるまでの間を倍にしていく（MAX_SECONDS まで）。しつこくしないため。
  人が話したら、元の間に戻す。
- 人が話している最中、シエルが考え中・話している最中は話しかけない。会話の始めのあいさつの前も話しかけない。
"""
import asyncio
import logging
import time

from livekit.agents import AgentSession

log = logging.getLogger('ciel-agent.initiative')

FIRST_SECONDS = 45.0    # 静かになってから、はじめて話しかけるまで
MAX_SECONDS = 600.0     # 返事がないときに、間をあける上限
CHECK_SECONDS = 2.0


class Initiative:
    def __init__(self, session: AgentSession, style, nudge: str) -> None:
        self.session = session
        self.style = style   # mode.ConversationStyle
        self.nudge = nudge
        self.interval = FIRST_SECONDS
        self._last = time.monotonic()      # 最後に誰かが話していた時刻
        self._user_busy = False
        self._agent_busy = True            # あいさつが終わるまでは話しかけない
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    def on_user_state(self, ev) -> None:
        self._user_busy = ev.new_state == 'speaking'
        self._last = time.monotonic()
        if self._user_busy:
            self.interval = FIRST_SECONDS   # 人が話したら、元の間に戻す

    def on_agent_state(self, ev) -> None:
        self._agent_busy = ev.new_state in ('thinking', 'speaking', 'initializing')
        self._last = time.monotonic()

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(CHECK_SECONDS)
            now = time.monotonic()
            if self.style.talk != 'chatty' or self._user_busy or self._agent_busy:
                if self.style.talk != 'chatty':
                    self._last = now   # おしゃべりにした時から数える
                continue
            if now - self._last < self.interval:
                continue
            log.info('おしゃべり：%.0f 秒静かなので、シエルから話しかける', now - self._last)
            self._last = now
            self.interval = min(self.interval * 2, MAX_SECONDS)
            try:
                self.session.generate_reply(instructions=self.nudge)
            except Exception as e:   # 話しかけられなくても、会話は続ける
                log.warning('話しかけられない: %s', e)
