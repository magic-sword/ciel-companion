# -*- coding: utf-8 -*-
"""歌を聴いた印象の手がかりを返すサービス（自宅の GPU。歌声は外へ送らない）。

POST /analyze  本文 = PCM（int16、リトルエンディアン、モノラル）、ヘッダー X-Sample-Rate（既定 16000）
  → 200、本文 JSON（analysis.analyze の結果。トリムした頭の秒数 offset も足す）
GET /health    → 200 {"ok": true}
歌声は受け取ったメモリーの中だけで扱い、ファイルにもログにも残さない。127.0.0.1 だけで待ち受ける（同じマシンの会話サーバー用）。
GPU は読み上げ（tts-irodori）と分け合うので、分析は 1 つずつ順に行う。

使うモデル（版は固定）：
- Meta Audiobox Aesthetics（facebook/audiobox-aesthetics、CC-BY 4.0）… 区間ごとの「聴いて楽しい・心に響く」（CE）
- MERT-v1-95M（m-a-p/MERT-v1-95M、CC-BY-NC 4.0：非商用。公開前に見直す）… 区間ごとの音楽の特徴（展開の変化）
- torchcrepe（MIT、CREPE tiny）… 音の高さ（アカペラ・ヘッドホンで伴奏を聴く想定。伴奏が混ざるなら RMVPE へ）

環境変数：SING_PORT（既定 8767）、SING_DEVICE（既定 cuda。無ければ cpu）、SING_CREPE（tiny・full）
"""
import json
import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import torch
import torchaudio
import torchcrepe
from audiobox_aesthetics.infer import AXES_NAME, Normalize
from audiobox_aesthetics.model.aes import AesMultiOutput
from transformers import AutoModel, Wav2Vec2FeatureExtractor

import analysis

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('singing')

PORT = int(os.environ.get('SING_PORT', '8767'))
DEVICE = os.environ.get('SING_DEVICE', 'cuda' if torch.cuda.is_available() else 'cpu')
MAX_SECONDS = 600          # これより長い歌は、頭から 10 分だけ見る
AES_REPO, AES_REVISION = 'facebook/audiobox-aesthetics', '9b1dd8e5df9af7216e836a98974fe3b82c56ded6'
MERT_REPO, MERT_REVISION = 'm-a-p/MERT-v1-95M', '12af15fef9d0ac838c3f475bfbbf26d2060dd4f5'
MERT_LAYER = 7             # 中ほどの層（曲の構造・音色の両方が出やすい）
# CREPE の大きさ。4 分の歌で full 24 秒・tiny 8 秒（RTX 2060）。合成の歌声で、両方とも声のある所の 99.8% が 50 セント以内で一致した
# （2026-10-27）。本物の歌で差が出たら full にする
CREPE_MODEL = os.environ.get('SING_CREPE', 'tiny')
LOCK = threading.Lock()


class Models:
    def __init__(self) -> None:
        t = time.time()
        self.aes = AesMultiOutput.from_pretrained(AES_REPO, revision=AES_REVISION).to(DEVICE).eval()
        self.aes_norm = {axis: Normalize(mean=self.aes.target_transform[axis]['mean'],
                                         std=self.aes.target_transform[axis]['std']) for axis in AXES_NAME}
        self.mert = AutoModel.from_pretrained(MERT_REPO, revision=MERT_REVISION, trust_remote_code=True).to(DEVICE).eval()
        self.mert_proc = Wav2Vec2FeatureExtractor.from_pretrained(MERT_REPO, revision=MERT_REVISION, trust_remote_code=True)
        log.info('モデルを読み込んだ（%.1f 秒、%s）', time.time() - t, DEVICE)

    @torch.inference_mode()
    def aesthetics(self, audio: np.ndarray, spans: list[tuple[float, float]]) -> list[dict]:
        """区間ごとの 4 つの軸（CE・CU・PC・PQ）。短い区間は 10 秒まで 0 で埋め、埋めた所は見ない"""
        n = int(analysis.WINDOW * analysis.SR)
        wavs, masks = [], []
        for a, b in spans:
            seg = torch.from_numpy(audio[int(a * analysis.SR):int(b * analysis.SR)].copy())[:n]
            mask = torch.zeros(1, n, dtype=torch.bool)
            mask[:, :len(seg)] = True
            wavs.append(torch.nn.functional.pad(seg, (0, n - len(seg)))[None])
            masks.append(mask)
        out = []
        for i in range(0, len(wavs), 8):
            preds = self.aes({'wav': torch.stack(wavs[i:i + 8]).to(DEVICE), 'mask': torch.stack(masks[i:i + 8]).to(DEVICE)})
            values = {axis: self.aes_norm[axis].inverse(preds[axis]).float().cpu().numpy() for axis in AXES_NAME}
            out += [{axis: float(values[axis][j]) for axis in AXES_NAME} for j in range(len(values[AXES_NAME[0]]))]
        return out

    @torch.inference_mode()
    def embeddings(self, audio: np.ndarray, spans: list[tuple[float, float]]) -> np.ndarray:
        """区間ごとの MERT の特徴（MERT_LAYER の層を時間で平均）。MERT は 24 kHz"""
        sr = self.mert_proc.sampling_rate
        wav = torchaudio.functional.resample(torch.from_numpy(audio.copy()), analysis.SR, sr).numpy()
        out = []
        for a, b in spans:
            seg = wav[int(a * sr):int(b * sr)]
            inputs = self.mert_proc(seg, sampling_rate=sr, return_tensors='pt').to(DEVICE)
            hidden = self.mert(**inputs, output_hidden_states=True).hidden_states[MERT_LAYER]
            out.append(hidden[0].mean(0).float().cpu().numpy())
        return np.stack(out) if out else np.zeros((0, 768))

    @torch.inference_mode()
    def pitch(self, audio: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        x = torch.from_numpy(audio.copy())[None]
        f0, periodicity = torchcrepe.predict(x, analysis.SR, hop_length=int(analysis.HOP * analysis.SR),
                                             fmin=65.0, fmax=1100.0, model=CREPE_MODEL, batch_size=512,
                                             device=DEVICE, return_periodicity=True)
        periodicity = torchcrepe.filter.median(periodicity, 3)
        f0 = torchcrepe.filter.mean(f0, 3)
        return f0[0].cpu().numpy(), periodicity[0].cpu().numpy()

    def analyze(self, audio: np.ndarray) -> dict:
        audio, offset = analysis.trim(audio[: MAX_SECONDS * analysis.SR])
        if len(audio) < analysis.SR:
            return {'empty': True, 'offset': round(offset, 1)}
        spans = analysis.windows(len(audio) / analysis.SR)
        t = time.time()
        aes = self.aesthetics(audio, spans)
        emb = self.embeddings(audio, spans)
        f0, periodicity = self.pitch(audio)
        result = analysis.analyze(audio, f0, periodicity, aes, emb, spans)
        result['offset'] = round(offset, 1)
        log.info('分析した：%.1f 秒の歌を %.1f 秒で', len(audio) / analysis.SR, time.time() - t)
        return result


MODELS: Models | None = None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != '/health':
            self.send_error(404)
            return
        self._json(200, {'ok': MODELS is not None})

    def do_POST(self) -> None:
        if self.path != '/analyze':
            self.send_error(404)
            return
        try:
            sr = int(self.headers.get('X-Sample-Rate', analysis.SR))
            length = int(self.headers.get('Content-Length', 0))
            pcm = np.frombuffer(self.rfile.read(length), dtype=np.int16).astype(np.float32) / 32768.0
            if sr != analysis.SR:
                pcm = torchaudio.functional.resample(torch.from_numpy(pcm), sr, analysis.SR).numpy()
            with LOCK:
                result = MODELS.analyze(pcm)
        except Exception as e:
            log.exception('分析できなかった')
            self._json(500, {'error': type(e).__name__})
            return
        self._json(200, result)

    def _json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args) -> None:   # 既定の 1 行ごとのログは出さない（ログは分析の結果の 1 行だけ）
        pass


if __name__ == '__main__':
    MODELS = Models()
    log.info('127.0.0.1:%d で待ち受けます', PORT)
    ThreadingHTTPServer(('127.0.0.1', PORT), Handler).serve_forever()
