# -*- coding: utf-8 -*-
"""Irodori-TTS の読み上げサービス：会話サーバーから文を受け取り、シエルの声で読み上げた音声を返す。

POST /synthesize  本文 JSON {"text": "...", "caption": "...（省略可）", "seconds": 0.6（省略可）}
  seconds … 音声の長さ（秒）。省略すると Irodori-TTS が文から長さを決める。短い相づち（server/agent/aizuchi.py）は
            決めさせると間延びする（「んー、」が 2 秒など）ので、長さを渡す
  省略可：cfg_caption（キャプションの効き。既定 3.0）、cfg_speaker（参照音声の効き。既定 5.0）、seed（揺れを固定する）
  → 200、本文 = PCM（int16、リトルエンディアン、モノラル）、ヘッダー X-Sample-Rate
GPU は 1 つなので、合成は 1 つのスレッドで 1 文ずつ順に行う。127.0.0.1 だけで待ち受ける（同じマシンの会話サーバー用）。
参照音声（/data/samples/*.wav、シエルのボイスサンプル）は起動時に 1 回だけ読み込んで符号化する（encode_refs）。

環境変数：TTS_PORT（既定 8766）、TTS_STEPS（既定 8。16 は標準の 40 と聞き分けられなかった。8・12・16 を同じ文・同じ種で聞き比べ、
  8 と 12 で違いが分からなかった（2026-10-22、利用者）。1 文あたり 16 より約 0.09 秒速い）
"""
import glob
import json
import logging
import os
import sys
import time
import uuid
from concurrent.futures import CancelledError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

from scheduler import FairScheduler, QueueFull

sys.path.insert(0, '/opt/irodori')
import numpy as np
import torch

import irodori_tts.attention as attention
from irodori_tts.inference_runtime import (InferenceRuntime, RuntimeKey, SamplingRequest, _load_audio,
                                           download_hf_checkpoint)
from torch.nn.attention import SDPBackend

# Irodori-TTS は注意の計算に cuDNN を優先して使う。cuDNN は音声の長さが変わるたびに計算の準備（約 0.8 秒）をし直すため、
# 会話では文ごとに 1 秒ほど遅れた。長さに関係なく速い EFFICIENT を使う（品質は同じ計算）
attention._SDPA_PRIORITY[:] = [SDPBackend.EFFICIENT_ATTENTION, SDPBackend.MATH]

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('tts-irodori')

# 設定資料 7.1 の通常の声
CAPTION = ('柔らかく朗らかな響きを持つ10代前半の少女。人懐っこく甘すぎないナチュラルなトーンで、聞く人を笑顔にする温かみのある声。'
           '無邪気で親しみやすく、一生懸命寄り添ってくれるパートナー風。')
STEPS = int(os.environ.get('TTS_STEPS', '8'))
REFS = sorted(glob.glob('/data/samples/*.wav'))
RT = InferenceRuntime.from_key(RuntimeKey(
    checkpoint=download_hf_checkpoint('Aratako/Irodori-TTS-v4.1-Small'), model_device='cuda',
    model_precision='bf16', codec_device='cuda', codec_precision='bf16'))
# 合成は 1 つの決まったスレッドで行う（新しいスレッドで初めて合成すると 1 秒ほど余計にかかったため）
WORKER = FairScheduler()


def encode_refs(paths: list[str]) -> str:
    """参照音声を、起動時に 1 回だけ潜在表現にして保存し、そのファイルの場所を返す。
    ref_wavs で渡すと、文ごとに参照音声を読み込んで符号化し直していた（1 文あたり約 0.16 秒。結果は毎回同じ）。
    Irodori-TTS が ref_wavs を受け取ったときと同じ処理（音量をそろえて符号化し、順につなぐ）を行う。
    同じ文・同じ種で、ref_wavs のときとまったく同じ音声になることを確かめた（2026-10-22）。"""
    req = SamplingRequest(text='')
    pieces = []
    for path in paths:
        wav, sr = _load_audio(path)
        pieces.append(RT.codec.encode_waveform(wav.unsqueeze(0), sample_rate=int(sr), normalize_db=req.ref_normalize_db,
                                               ensure_max=bool(req.ref_ensure_max)).cpu())
    out = os.path.join('/tmp', 'ciel-ref-latent.pt')
    torch.save(torch.cat(pieces, dim=1)[0], out)
    return out


REF_LATENT = encode_refs(REFS)


def synthesize(text: str, caption: str | None, seconds: float | None = None,
               session_id='legacy', request_id=None, **options):
    request_id = request_id or uuid.uuid4().hex
    future = WORKER.submit(session_id, request_id, lambda: _synthesize(text, caption, seconds, **options))
    try:
        result, queued = future.result(timeout=30)
        log.info('synthesis session=%s request=%s queue_ms=%.0f', session_id, request_id, queued * 1000)
        return (*result, queued)
    finally:
        WORKER.cancel(session_id, request_id)


def _synthesize(text: str, caption: str | None, seconds: float | None = None, **options):
    """options：SamplingRequest の cfg_scale_caption・cfg_scale_speaker・seed（省略すると Irodori-TTS の既定）"""
    t = time.perf_counter()
    # 長さを渡すときは、下限（既定 0.5 秒）もそれに合わせて下げる
    length = {} if seconds is None else {'seconds': seconds, 'min_seconds': min(0.5, seconds)}
    r = RT.synthesize(SamplingRequest(text=text, caption=caption or CAPTION, ref_latents=[REF_LATENT], num_steps=STEPS,
                                      **length, **options), log_fn=None)
    audio = r.audio.squeeze().float().cpu().numpy()
    dt = time.perf_counter() - t
    log.info('synthesis compute_ms=%.0f audio_ms=%.0f', dt * 1000, len(audio) / r.sample_rate * 1000)
    pcm = (np.clip(audio, -1, 1) * 32767).astype('<i2').tobytes()
    return pcm, r.sample_rate


class Handler(BaseHTTPRequestHandler):
    def do_DELETE(self):
        path = urlsplit(self.path)
        if not path.path.startswith('/synthesize/'):
            self.send_error(404)
            return
        session = parse_qs(path.query).get('session_id', [''])[0]
        WORKER.cancel(session, path.path.removeprefix('/synthesize/'))
        self.send_response(204)
        self.end_headers()

    def do_POST(self):
        if self.path != '/synthesize':
            self.send_error(404)
            return
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        session_id, request_id = body.get('session_id', 'legacy'), body.get('request_id', uuid.uuid4().hex)
        if any(not isinstance(v, str) or not v or len(v) > 128 or not all(c.isalnum() or c in '-_' for c in v)
               for v in (session_id, request_id)):
            self.send_error(400, 'invalid session or request ID')
            return
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
            pcm, sr, queued = synthesize(text, body.get('caption'), seconds,
                                        session_id=session_id, request_id=request_id, **options)
        except QueueFull:
            self.send_error(429, 'synthesis queue is full')
            return
        except (TimeoutError, CancelledError):
            self.send_error(408, 'synthesis expired or cancelled')
            return
        except Exception as e:   # 1 文の失敗でサービスを止めない
            log.exception('合成に失敗')
            self.send_error(500, str(e)[:200])
            return
        self.send_response(200)
        self.send_header('Content-Type', 'audio/pcm')
        self.send_header('X-Sample-Rate', str(sr))
        self.send_header('X-Queue-Ms', str(round(queued * 1000)))
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
