# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""声質変換サービスの確認：wav を実時間の速さで送り、変換した音声を保存して、遅れと処理の速さを測る。
実行  python bench.py 入力.wav 出力.wav [ws://127.0.0.1:8765]
"""
import asyncio
import json
import sys
import time

import librosa
import numpy as np
import soundfile as sf
import websockets

SR = 24000
CHUNK = 0.05   # OpenAI の音声と同じくらいの細かさで送る（秒）


async def main():
    src, dst = sys.argv[1:3]
    url = sys.argv[3] if len(sys.argv) > 3 else 'ws://127.0.0.1:8765'
    x, _ = librosa.load(src, sr=SR)
    first_in = None
    first_out = None
    out = []
    arrivals = []   # (それまでに届いたサンプル数, 時刻)
    async with websockets.connect(url, max_size=2 ** 22) as ws:
        async def recv():
            nonlocal first_out
            async for m in ws:
                if isinstance(m, bytes):
                    if first_out is None:
                        first_out = time.perf_counter()
                    out.append(np.frombuffer(m, dtype='<f4'))
                    arrivals.append((sum(len(o) for o in out), time.perf_counter()))
                elif json.loads(m).get('type') == 'flushed':
                    return
        r = asyncio.create_task(recv())
        n = int(SR * CHUNK)
        t0 = time.perf_counter()
        for i in range(0, len(x), n):
            # 声が始まった時刻（音量が上がった最初のかたまり）
            if first_in is None and np.sqrt(np.mean(x[i:i + n] ** 2)) > 0.01:
                first_in = time.perf_counter()
            await ws.send(x[i:i + n].astype('<f4').tobytes())
            await asyncio.sleep(max(0, t0 + (i + n) / SR - time.perf_counter()))
        await ws.send(json.dumps({'type': 'flush'}))
        await r
    y = np.concatenate(out) if out else np.zeros(0)
    sf.write(dst, y, SR)
    # 出力の中で声が始まる位置
    k = next((i for i in range(0, len(y), 240) if np.sqrt(np.mean(y[i:i + 240] ** 2)) > 0.01), None)
    print('入力 %.2f 秒、出力 %.2f 秒' % (len(x) / SR, len(y) / SR))
    if k is not None:
        kin = next(i for i in range(0, len(x), 240) if np.sqrt(np.mean(x[i:i + 240] ** 2)) > 0.01)
        sent = t0 + kin / SR                                   # 入力の声の始まりを送った時刻
        got = next(t for n, t in arrivals if n > k)            # 出力の声の始まりが届いた時刻
        print('音声の中の声の始まりのずれ %.3f 秒' % ((k - kin) / SR))
        print('変換による遅れ（声の始まりを送ってから、変換した声の始まりが届くまで） %.3f 秒' % (got - sent))


asyncio.run(main())
