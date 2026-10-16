# -*- coding: utf-8 -*-
"""シエルの声の大きさ。Unity の設定画面で選んだ大きさ（LiveKit のデータのメッセージ、topic ciel.volume）を受け取り、
アプリへ送る声にかける。

- アプリの声の再生（LiveKit の端末の音声）には音量を変える手段がないので、送る前にここで小さくする。
- 大きさは 0〜1（1 がそのまま）。1 より大きくはしない（音が割れるため。大きくしたいときは端末の音量を上げる）。
- Unity は、つないだとき・会話サーバーが部屋に入ったとき・大きさを変えたときに送る。同じ値が何度届いてもよい。
- 大きさが変わったときは、1 つの音の区切りの中でなめらかに変える（急に変えるとプツッと鳴る）。
"""
import json
import logging
from collections.abc import AsyncIterable

import numpy as np
from livekit import rtc

log = logging.getLogger('ciel-agent.volume')

TOPIC = 'ciel.volume'


class VoiceVolume:
    def __init__(self) -> None:
        self.volume = 1.0
        self._applied = 1.0   # 直前に送った声にかけた大きさ

    def on_data(self, packet: rtc.DataPacket) -> None:
        if packet.topic != TOPIC:
            return
        try:
            volume = float(json.loads(packet.data.decode('utf-8'))['volume'])
        except (ValueError, KeyError, TypeError) as ex:
            log.warning('声の大きさのメッセージを読めない: %s', ex)
            return
        volume = min(max(volume, 0.0), 1.0)
        if volume != self.volume:
            self.volume = volume
            log.info('声の大きさ：%.2f', volume)

    async def apply(self, frames: AsyncIterable[rtc.AudioFrame]) -> AsyncIterable[rtc.AudioFrame]:
        """frames の声に、いまの大きさをかけて順に返す。"""
        async for frame in frames:
            start, end = self._applied, self.volume
            self._applied = end
            if start == 1.0 and end == 1.0:
                yield frame
                continue
            pcm = np.frombuffer(frame.data, dtype=np.int16).astype(np.float32)
            n = frame.samples_per_channel
            gain = np.linspace(start, end, n, dtype=np.float32) if start != end else np.float32(end)
            pcm = pcm.reshape(n, frame.num_channels) * (gain[:, None] if start != end else gain)
            out = np.clip(pcm, -32768, 32767).astype(np.int16)
            yield rtc.AudioFrame(out.tobytes(), frame.sample_rate, frame.num_channels, n)
