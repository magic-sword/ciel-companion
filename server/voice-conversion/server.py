# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""声質変換サービス：WebSocket で届いた音声を、シエルの声へ変換して返す（同じマシンの会話サーバーから使う）。

接続 1 本 = 音声の流れ 1 本（OpenAI の 1 回の返事）。
  クライアント → サーバー：バイナリ = PCM（float32、リトルエンディアン、モノラル、IN_SR Hz）
                          テキスト {"type": "flush"} = 入力の終わり（残りを出し切る）
  サーバー → クライアント：バイナリ = 変換した PCM（同じ形式、IN_SR Hz）
                          テキスト {"type": "flushed"} = 出し切った
GPU は 1 つなので、変換は 1 本ずつ順に行う（ロック）。

起動  python server.py   環境変数：VC_REFERENCE（参照音声の wav）、VC_PORT（既定 8765、127.0.0.1 のみで待つ）
"""
import asyncio
import json
import logging
import os
import time

import librosa
import numpy as np
import soxr
import websockets

import stream_vc

IN_SR = 24000   # OpenAI の音声の標本化周波数
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('voice-conversion')

MODEL = stream_vc.load('cuda')
SR = MODEL[-1]['sampling_rate']
REF_PATH = os.environ.get('VC_REFERENCE', '/data/reference.wav')
REF, _ = librosa.load(REF_PATH, sr=SR)
LOCK = asyncio.Lock()
log.info('モデルを読み込んだ（SR=%d）。参照音声 %s（%.1f 秒）', SR, REF_PATH, len(REF) / SR)


def warmup():
    conv = stream_vc.StreamConverter(MODEL, REF, REF_PATH)
    t = time.perf_counter()
    conv.push(np.random.randn(SR).astype(np.float32) * 0.05)
    log.info('ウォームアップ %.2f 秒', time.perf_counter() - t)


async def handle(ws):
    conv = stream_vc.StreamConverter(MODEL, REF, REF_PATH)
    down = soxr.ResampleStream(IN_SR, SR, 1, dtype='float32')
    up = soxr.ResampleStream(SR, IN_SR, 1, dtype='float32')
    total_in = total_busy = 0.0
    try:
        async for msg in ws:
            if isinstance(msg, bytes):
                pcm = np.frombuffer(msg, dtype='<f4')
                total_in += len(pcm) / IN_SR
                x = down.resample_chunk(pcm)
                async with LOCK:
                    t = time.perf_counter()
                    y = await asyncio.to_thread(conv.push, x)
                    total_busy += time.perf_counter() - t
                if len(y):
                    await ws.send(up.resample_chunk(y).astype('<f4').tobytes())
            else:
                if json.loads(msg).get('type') == 'flush':
                    async with LOCK:
                        y = await asyncio.to_thread(conv.flush)
                    out = up.resample_chunk(y, last=True)
                    if len(out):
                        await ws.send(out.astype('<f4').tobytes())
                    await ws.send(json.dumps({'type': 'flushed'}))
    except websockets.ConnectionClosed:
        pass
    finally:
        if total_in:
            log.info('流れ 1 本：入力 %.1f 秒、変換の処理 %.2f 秒（実時間比 %.2f）', total_in, total_busy, total_busy / total_in)


async def main():
    await asyncio.to_thread(warmup)
    port = int(os.environ.get('VC_PORT', '8765'))
    async with websockets.serve(handle, '127.0.0.1', port, max_size=2 ** 22):
        log.info('待ち受け 127.0.0.1:%d', port)
        await asyncio.Future()


if __name__ == '__main__':
    asyncio.run(main())
