# -*- coding: utf-8 -*-
"""Irodori-TTS の読み上げサービス：会話サーバーから文を受け取り、シエルの声で読み上げた音声を返す。

POST /synthesize  本文 JSON {"text": "...", "caption": "...（省略可）", "seconds": 0.6（省略可）}
  seconds … 音声の長さ（秒）。省略すると Irodori-TTS が文から長さを決める。短い相づち（server/agent/aizuchi.py）は
            決めさせると間延びする（「んー、」が 2 秒など）ので、長さを渡す
  省略可：cfg_caption（キャプションの効き。既定 3.0）、cfg_speaker（参照音声の効き。既定 5.0）、seed（揺れを固定する）
  → 200、本文 = PCM（int16、リトルエンディアン、モノラル）、ヘッダー X-Sample-Rate
GPU は 1 つなので、合成は 1 つのスレッドで 1 文ずつ順に行う。127.0.0.1 だけで待ち受ける（同じマシンの会話サーバー用）。
参照音声（/data/samples/*.wav、シエルのボイスサンプル）は起動時に 1 回だけ読み込む。

環境変数：TTS_PORT（既定 8766）、TTS_STEPS（既定 16。標準の 40 と聞き分けられない品質だった）
"""
import glob
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, '/opt/irodori')
import numpy as np
import torch

import irodori_tts.attention as attention
from irodori_tts.inference_runtime import InferenceRuntime, RuntimeKey, SamplingRequest, download_hf_checkpoint
from torch.nn.attention import SDPBackend

# Irodori-TTS は注意の計算に cuDNN を優先して使う。cuDNN は音声の長さが変わるたびに計算の準備（約 0.8 秒）をし直すため、
# 会話では文ごとに 1 秒ほど遅れた。長さに関係なく速い EFFICIENT を使う（品質は同じ計算）
attention._SDPA_PRIORITY[:] = [SDPBackend.EFFICIENT_ATTENTION, SDPBackend.MATH]

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('tts-irodori')

# 設定資料 7.1 の通常の声
CAPTION = ('柔らかく朗らかな響きを持つ10代前半の少女。人懐っこく甘すぎないナチュラルなトーンで、聞く人を笑顔にする温かみのある声。'
           '無邪気で親しみやすく、一生懸命寄り添ってくれるパートナー風。')
STEPS = int(os.environ.get('TTS_STEPS', '16'))
REFS = sorted(glob.glob('/data/samples/*.wav'))
RT = InferenceRuntime.from_key(RuntimeKey(
    checkpoint=download_hf_checkpoint('Aratako/Irodori-TTS-v4.1-Small'), model_device='cuda',
    model_precision='bf16', codec_device='cuda', codec_precision='bf16'))
# 合成は 1 つの決まったスレッドで行う（新しいスレッドで初めて合成すると 1 秒ほど余計にかかったため）
WORKER = ThreadPoolExecutor(max_workers=1)


def synthesize(text: str, caption: str | None, seconds: float | None = None, **options):
    return WORKER.submit(_synthesize, text, caption, seconds, **options).result()


def _synthesize(text: str, caption: str | None, seconds: float | None = None, **options):
    """options：SamplingRequest の cfg_scale_caption・cfg_scale_speaker・seed（省略すると Irodori-TTS の既定）"""
    t = time.perf_counter()
    # 長さを渡すときは、下限（既定 0.5 秒）もそれに合わせて下げる
    length = {} if seconds is None else {'seconds': seconds, 'min_seconds': min(0.5, seconds)}
    r = RT.synthesize(SamplingRequest(text=text, caption=caption or CAPTION, ref_wavs=REFS, num_steps=STEPS,
                                      **length, **options), log_fn=None)
    audio = r.audio.squeeze().float().cpu().numpy()
    dt = time.perf_counter() - t
    log.info('合成 %.2f 秒 / 音声 %.2f 秒：%s', dt, len(audio) / r.sample_rate, text[:30])
    pcm = (np.clip(audio, -1, 1) * 32767).astype('<i2').tobytes()
    return pcm, r.sample_rate


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/synthesize':
            self.send_error(404)
            return
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        text = str(body.get('text', '')).strip()
        if not text:
            self.send_error(400, 'text is empty')
            return
        seconds = body.get('seconds')
        try:
            seconds = None if seconds is None else float(seconds)
            if seconds is not None and not 0.1 <= seconds <= 30:
                raise ValueError
        except (TypeError, ValueError):
            self.send_error(400, 'seconds must be 0.1-30')
            return
        options = {}
        try:
            for key, name in (('cfg_caption', 'cfg_scale_caption'), ('cfg_speaker', 'cfg_scale_speaker')):
                if body.get(key) is not None:
                    options[name] = float(body[key])
                    if not 0 <= options[name] <= 10:
                        raise ValueError
            if body.get('seed') is not None:
                options['seed'] = int(body['seed'])
        except (TypeError, ValueError):
            self.send_error(400, 'cfg_caption / cfg_speaker must be 0-10, seed an integer')
            return
        try:
            pcm, sr = synthesize(text, body.get('caption'), seconds, **options)
        except Exception as e:   # 1 文の失敗でサービスを止めない
            log.exception('合成に失敗')
            self.send_error(500, str(e)[:200])
            return
        self.send_response(200)
        self.send_header('Content-Type', 'audio/pcm')
        self.send_header('X-Sample-Rate', str(sr))
        self.send_header('Content-Length', str(len(pcm)))
        self.end_headers()
        self.wfile.write(pcm)

    def log_message(self, *args):
        pass


if __name__ == '__main__':
    synthesize('ウォームアップです。', None)
    port = int(os.environ.get('TTS_PORT', '8766'))
    log.info('待ち受け 127.0.0.1:%d（%d ステップ、参照音声 %d 本）', port, STEPS, len(REFS))
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
