# -*- coding: utf-8 -*-
"""OpenAI の声を、声質変換サービス（../voice-conversion、同じマシンの WebSocket）でシエルの声に変えてから流す。

返事 1 回ごとに接続を 1 本開き、届いた音声のかたまりを送り、変換された音声を受け取りしだい返す。
返事の音声が終わったら、変換の遅れの分を出し切る（flush）。割り込みで返事が止まると、この処理も取り消され、
接続を閉じる（古い音声は流れない）。
変換サービスにつながらないときは、黙って元の声へ切り替えない（仕様書 5.1）。音を止めて、ログに残す。
"""
import asyncio
import json
import logging
import os
from collections.abc import AsyncIterable

import numpy as np
import websockets
from livekit import rtc

log = logging.getLogger('ciel-agent.vc')
URL = os.environ.get('CIEL_VC_URL', 'ws://127.0.0.1:8765')
SR = 24000
OUT_FRAME = SR // 50   # 20 ms ずつ返す


def _to_float(frame: rtc.AudioFrame) -> np.ndarray:
    pcm = np.frombuffer(frame.data, dtype=np.int16).astype(np.float32) / 32768.0
    if frame.num_channels > 1:
        pcm = pcm.reshape(-1, frame.num_channels).mean(axis=1)
    return pcm


def _frame(pcm: np.ndarray) -> rtc.AudioFrame:
    data = (np.clip(pcm, -1, 1) * 32767).astype(np.int16)
    return rtc.AudioFrame(data.tobytes(), SR, 1, len(data))


async def convert(audio: AsyncIterable[rtc.AudioFrame]):
    """audio（OpenAI の声、24 kHz）を変換した rtc.AudioFrame を順に返す。"""
    try:
        ws = await websockets.connect(URL, max_size=2 ** 22)
    except OSError as e:
        log.error('声質変換サービスにつながらない（%s）。この返事は流さない', e)
        async for _ in audio:
            pass
        return
    out: asyncio.Queue = asyncio.Queue()

    async def receive():
        try:
            async for m in ws:
                if isinstance(m, bytes):
                    await out.put(np.frombuffer(m, dtype='<f4'))
                elif json.loads(m).get('type') == 'flushed':
                    break
        finally:
            await out.put(None)

    async def send():
        async for frame in audio:
            if frame.sample_rate != SR:
                log.warning('想定外の標本化周波数 %d', frame.sample_rate)
            await ws.send(_to_float(frame).astype('<f4').tobytes())
        await ws.send(json.dumps({'type': 'flush'}))

    rx = asyncio.create_task(receive())
    tx = asyncio.create_task(send())
    rest = np.zeros(0, dtype=np.float32)
    try:
        while True:
            chunk = await out.get()
            if chunk is None:
                break
            rest = np.concatenate([rest, chunk])
            while len(rest) >= OUT_FRAME:
                yield _frame(rest[:OUT_FRAME])
                rest = rest[OUT_FRAME:]
        if len(rest):
            yield _frame(rest)
    finally:
        tx.cancel()
        rx.cancel()
        await ws.close()
