# -*- coding: utf-8 -*-
"""タッチ：Unity で相手がシエルに触れたこと（LiveKit のデータのメッセージ、topic ciel.touch）を受け取り、
会話モデルに「[タッチ] 頭を撫でる（2.4秒）」のような 1 行で知らせて、反応を話してもらう。

- 触れた瞬間の顔の動き・髪の揺れは Unity がその場で出す。ここでは声の反応だけを扱う。
- シエルが話している・考えている間や、相手が話している間は割り込まない。撫でている途中で返せなかったときは、
  撫で終わり（phase end）で返す。短い間に何度も返さないよう、間隔をあける。
- 知らせの受け取り方は config/prompts/touch.md でモデルに教える。
"""
import json
import logging
import time

from livekit import rtc
from livekit.agents import AgentSession

log = logging.getLogger('ciel-agent.touch')

TOPIC = 'ciel.touch'
# Unity（CielTouch）が送る部位・しぐさ。ほかの値は無視する
PARTS = {'head': '頭', 'ear': '耳', 'face': 'ほっぺ', 'hair': '髪', 'shoulder': '肩', 'hand': '手'}
GESTURES = {'tap': 'ちょんとつつく', 'stroke': '撫でる', 'hold': 'そっと触れる'}
PHASES = {'once', 'start', 'end'}   # once：tap・hold を離したとき。start・end：なぞりの始まりと終わり
COOLDOWN = 4.0   # 返事の最短の間隔（秒）


def describe(part: str, gesture: str, phase: str, duration_ms: int) -> str:
    line = f'[タッチ] {PARTS[part]}を{GESTURES[gesture]}'
    if phase == 'start':
        return line + '（撫で始めた）'
    if duration_ms > 0:
        return line + f'（{duration_ms / 1000:.1f}秒）'
    return line


class TouchReactions:
    def __init__(self, session: AgentSession) -> None:
        self.session = session
        self.last_reply = 0.0
        self.stroke_answered = False

    def on_data(self, packet: rtc.DataPacket) -> None:
        if packet.topic != TOPIC:
            return
        try:
            e = json.loads(packet.data.decode('utf-8'))
            part, gesture, phase = e['part'], e['gesture'], e['phase']
            duration_ms = int(e.get('duration_ms', 0))
        except (ValueError, KeyError, TypeError) as ex:
            log.warning('タッチのメッセージを読めない: %s', ex)
            return
        if part not in PARTS or gesture not in GESTURES or phase not in PHASES:
            log.warning('知らないタッチ: %s %s %s', part, gesture, phase)
            return

        if phase == 'start':
            self.stroke_answered = self.reply(describe(part, gesture, phase, duration_ms))
        elif phase == 'end':
            # 撫でている途中で返せなかったときだけ、撫で終わりで返す
            if not self.stroke_answered:
                self.reply(describe(part, gesture, phase, duration_ms))
            self.stroke_answered = False
        else:
            self.reply(describe(part, gesture, phase, duration_ms))

    def reply(self, line: str) -> bool:
        s = self.session
        now = time.monotonic()
        if (s.agent_state in ('speaking', 'thinking') or s.user_state == 'speaking'
                or now - self.last_reply < COOLDOWN):
            log.debug('タッチに返事をしない（agent=%s user=%s）', s.agent_state, s.user_state)
            return False
        self.last_reply = now
        log.debug('タッチに返事をする')
        # 知らせを会話の履歴に残し、あとの会話でも触れられたことを覚えておけるようにする
        s.generate_reply(user_input=line)
        return True
