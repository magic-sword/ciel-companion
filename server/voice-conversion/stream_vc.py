# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
"""Seed-VC のリアルタイム変換を、マイクではなく、届いた音声のかたまりに対して行う（1 本の音声の流れごとに 1 つ）。

Seed-VC の real-time-gui.py（GPL-3.0、https://github.com/Plachtaa/seed-vc ）の start_vc と audio_callback の
処理（入力の窓をずらしながら変換し、SOLA で前の出力となめらかにつなぐ）を、そのまま関数にしたもの。
モデルの読み込みと 1 回分の変換（load_models・custom_infer）は real-time-gui.py のものを使う。
音声を聞くための VAD（funasr）は使わず、入力の音量が小さいかたまりは無音を返す。

時間の単位：サンプル数はモデルの標本化周波数（SR、22050 Hz）。block_time ごとに 1 回変換する。
変換による遅れは およそ block_time + crossfade_time + extra_time_right ＋ 処理時間。
"""
import importlib.util
import os

import numpy as np
import torch
import torch.nn.functional as F

SEED_VC_DIR = os.environ.get('SEED_VC_DIR', '/opt/seed-vc')

_spec = importlib.util.spec_from_file_location('seedvc_rt', os.path.join(SEED_VC_DIR, 'real-time-gui.py'))
rt = importlib.util.module_from_spec(_spec)


class Args:
    fp16 = True
    checkpoint_path = None   # 既定：Plachta/Seed-VC の DiT_uvit_tat_xlsr_ema.pth（tiny、リアルタイム用）
    config_path = None


def load(device='cuda'):
    """モデルを読み込む（プロセスで 1 回）。"""
    cwd = os.getcwd()
    os.chdir(SEED_VC_DIR)   # configs/ と checkpoints/ を相対パスで読むため
    try:
        _spec.loader.exec_module(rt)
        rt.device = torch.device(device)
        model_set = rt.load_models(Args())
    finally:
        os.chdir(cwd)
    return model_set


class Settings:
    block_time = 0.18        # 1 回に変換する長さ（秒）。短いほど遅れが小さく、処理は重い
    crossfade_time = 0.04
    extra_time_ce = 2.5      # 内容の読み取りに使う、過去の文脈（秒）
    extra_time = 0.5         # 変換（DiT）に使う、過去の文脈（秒）
    extra_time_right = 0.02  # 未来の文脈（秒）。遅れに直接足される
    diffusion_steps = 8
    inference_cfg_rate = 0.7
    max_prompt_length = 3.0  # 参照音声のうち使う長さ（秒）
    silence_rms = 0.003      # これより小さい入力のかたまりは無音を返す


class StreamConverter:
    """1 本の音声の流れ（OpenAI の 1 回の返事など）を変換する。push で入力を足し、変換できた分を返す。"""

    def __init__(self, model_set, reference_wav: np.ndarray, reference_name: str, s: Settings = Settings()):
        self.model_set = model_set
        self.s = s
        self.ref = reference_wav
        self.ref_name = reference_name
        self.sr = model_set[-1]['sampling_rate']
        dev = rt.device
        sr = self.sr
        self.zc = sr // 50

        def frames(sec):
            return int(np.round(sec * sr / self.zc)) * self.zc
        self.block_frame = frames(s.block_time)
        self.block_frame_16k = 320 * self.block_frame // self.zc
        self.crossfade_frame = frames(s.crossfade_time)
        self.sola_buffer_frame = min(self.crossfade_frame, 4 * self.zc)
        self.sola_search_frame = self.zc
        self.extra_frame = frames(s.extra_time_ce)
        self.extra_frame_right = frames(s.extra_time_right)
        n = self.extra_frame + self.crossfade_frame + self.sola_search_frame + self.block_frame + self.extra_frame_right
        self.input_wav = torch.zeros(n, device=dev, dtype=torch.float32)
        self.input_wav_res = torch.zeros(320 * n // self.zc, device=dev, dtype=torch.float32)
        self.sola_buffer = torch.zeros(self.sola_buffer_frame, device=dev, dtype=torch.float32)
        self.skip_head = self.extra_frame // self.zc
        self.skip_tail = self.extra_frame_right // self.zc
        self.return_length = (self.block_frame + self.sola_buffer_frame + self.sola_search_frame) // self.zc
        self.fade_in = torch.sin(0.5 * np.pi * torch.linspace(0.0, 1.0, steps=self.sola_buffer_frame, device=dev)) ** 2
        self.fade_out = 1 - self.fade_in
        self.pending = np.zeros(0, dtype=np.float32)
        # 変換の遅れ（入力の始まりから、その音が出力に出るまで）のサンプル数
        self.latency_frames = self.block_frame + self.sola_buffer_frame + self.extra_frame_right

    def push(self, pcm: np.ndarray) -> np.ndarray:
        """入力（SR、float32、モノラル）を足し、変換できたブロックをつないで返す（無ければ長さ 0）。"""
        self.pending = np.concatenate([self.pending, pcm.astype(np.float32)])
        outs = []
        while len(self.pending) >= self.block_frame:
            block, self.pending = self.pending[:self.block_frame], self.pending[self.block_frame:]
            outs.append(self._block(block))
        return np.concatenate(outs) if outs else np.zeros(0, dtype=np.float32)

    def flush(self) -> np.ndarray:
        """入力の終わり：遅れの分の無音を流して、最後の音まで出力する。"""
        return self.push(np.zeros(self.latency_frames + self.block_frame, dtype=np.float32))

    @torch.no_grad()
    def _block(self, indata: np.ndarray) -> np.ndarray:
        import librosa
        s = self.s
        dev = rt.device
        bf, zc = self.block_frame, self.zc
        self.input_wav[:-bf] = self.input_wav[bf:].clone()
        self.input_wav[-bf:] = torch.from_numpy(indata).to(dev)
        self.input_wav_res[:-self.block_frame_16k] = self.input_wav_res[self.block_frame_16k:].clone()
        self.input_wav_res[-320 * (bf // zc + 1):] = torch.from_numpy(
            librosa.resample(self.input_wav[-bf - 2 * zc:].cpu().numpy(), orig_sr=self.sr, target_sr=16000)[320:])

        # 文脈も含めて全部が静かなら、変換しない（無音）
        recent = self.input_wav[-(bf + self.extra_frame_right + self.sola_buffer_frame + self.sola_search_frame):]
        if float(torch.sqrt(torch.mean(recent ** 2))) < s.silence_rms:
            infer_wav = torch.zeros(self.input_wav.shape[0] - self.extra_frame, device=dev)
        else:
            infer_wav = rt.custom_infer(
                self.model_set, self.ref, self.ref_name, self.input_wav_res, self.block_frame_16k,
                self.skip_head, self.skip_tail, self.return_length, int(s.diffusion_steps),
                s.inference_cfg_rate, s.max_prompt_length, s.extra_time_ce - s.extra_time)

        # SOLA（DDSP-SVC 由来）：前の出力の終わりと最もよく重なる位置で、なめらかにつなぐ
        conv_input = infer_wav[None, None, : self.sola_buffer_frame + self.sola_search_frame]
        cor_nom = F.conv1d(conv_input, self.sola_buffer[None, None, :])
        cor_den = torch.sqrt(F.conv1d(conv_input ** 2, torch.ones(1, 1, self.sola_buffer_frame, device=dev)) + 1e-8)
        t = cor_nom[0, 0] / cor_den[0, 0]
        off = int(torch.argmax(t).item()) if t.numel() > 1 else 0
        infer_wav = infer_wav[off:]
        infer_wav[: self.sola_buffer_frame] *= self.fade_in
        infer_wav[: self.sola_buffer_frame] += self.sola_buffer * self.fade_out
        self.sola_buffer[:] = infer_wav[bf: bf + self.sola_buffer_frame]
        return infer_wav[:bf].float().cpu().numpy()
