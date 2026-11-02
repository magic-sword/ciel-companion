# -*- coding: utf-8 -*-
"""音の確かめ：アプリの「シエルの声を試しに流す」（LiveKit のデータのメッセージ、topic ciel.soundcheck）で、
決まった一言を読み上げて流す。会議につなぐ前に、シエルの声が仮想オーディオケーブルを通って会議へ届くかを確かめる。

- 会話モデル（OpenAI）を使わない。読み上げ（Irodori-TTS）だけで流すので、会話モデルが使えないとき（残高切れなど）も確かめられる。
- 声は相づちのトラック（aizuchi.py）で流す。シエルの声のトラックへ横から入れると、LiveKit の再生の管理とぶつかる（aizuchi.py の説明）。
  アプリは相づちのトラックも同じ「声の出力」で鳴らすので、確かめたい道筋は同じ。
- 一言は最初に頼まれたときに読み上げ、この会話の間は覚えておく（2 回目からはすぐ流す）。
- 結果はアプリへ voice.test（topic ciel.event）で知らせる：playing（流し始めた）・failed（流せない。reason：not_ready・tts）。
"""
import asyncio
import json
import logging

import aiohttp
from livekit import rtc

import aizuchi
import emotion

log = logging.getLogger('ciel-agent.soundcheck')

TOPIC = 'ciel.soundcheck'
LINE = 'シエルです。わたしの声、聞こえていますか？'
CAPTION = emotion.BASE + 'はっきりと明るく、相手に呼びかける。'


class SoundCheck:
    def __init__(self, backchannel, publish) -> None:
        self.backchannel = backchannel   # aizuchi.Backchannel（相づちのトラック。無ければ None）
        self.publish = publish           # アプリへの知らせ（agent.py の notify）
        self._frames: list[rtc.AudioFrame] | None = None
        self._task: asyncio.Task | None = None

    def on_data(self, packet: rtc.DataPacket) -> None:
        if packet.topic != TOPIC:
            return
        try:
            kind = json.loads(packet.data.decode('utf-8')).get('type')
        except (ValueError, AttributeError) as ex:
            log.warning('音の確かめのメッセージを読めない: %s', ex)
            return
        if kind != 'voice.test' or (self._task is not None and not self._task.done()):
            return
        self._task = asyncio.create_task(self.play())

    async def play(self) -> None:
        b = self.backchannel
        if b is None or not b.ready:
            log.info('音の確かめ：相づちのトラックがまだ無いので流せない')
            self._tell('failed', 'not_ready')
            return
        if self._frames is None:
            try:
                async with aiohttp.ClientSession() as http:
                    pcm, sr = await emotion.synthesize(http, LINE, CAPTION)
            except Exception as e:
                log.warning('音の確かめ：読み上げられない: %s', type(e).__name__)
                self._tell('failed', 'tts')
                return
            self._frames = b.fit(aizuchi.trim(pcm, sr), sr)
        log.info('音の確かめ：シエルの声を流す')
        b.play_frames(self._frames)
        self._tell('playing')

    def _tell(self, state: str, reason: str = '') -> None:
        self.publish({'v': 1, 'type': 'voice.test', 'state': state, **({'reason': reason} if reason else {})})
