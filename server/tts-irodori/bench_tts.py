# -*- coding: utf-8 -*-
"""Irodori-TTS で、シエルの声を直接読み上げる速さと品質を測る（比較用）。

参照音声：/data/samples/*.wav（ボイスサンプル）。キャプション：設定資料 7.1 の通常の声。
会話の 1 文ずつ（OpenAI が返す文を想定）を合成し、合成にかかった時間と、音声の長さ（実時間比）を記録する。
条件を変えて（モデルの精度、手順の数、コーデックを GPU に置くか）比べる。出力 /data/out/*.wav、/data/out/result.txt
"""
import glob
import os
import sys
import time

sys.path.insert(0, '/opt/irodori')
import soundfile as sf
import torch

from irodori_tts.inference_runtime import InferenceRuntime, RuntimeKey, SamplingRequest, download_hf_checkpoint

CAPTION = ('柔らかく朗らかな響きを持つ10代前半の少女。人懐っこく甘すぎないナチュラルなトーンで、聞く人を笑顔にする温かみのある声。'
           '無邪気で親しみやすく、一生懸命寄り添ってくれるパートナー風。')
SENTENCES = [
    'こんにちは！',
    '今日はどんな一日でしたか？',
    'ワタシは、あなたとお話しできるのを、ずっと楽しみにしていたのです。',
    'わふっ！？それは大発見なのです！くわしく教えてください！',
]
OUT = '/data/out'


def main():
    os.makedirs(OUT, exist_ok=True)
    refs = sorted(glob.glob('/data/samples/*.wav'))
    ckpt = download_hf_checkpoint('Aratako/Irodori-TTS-v4.1-Small')
    lines = []
    conds = [
        ('bf16-gpucodec', dict(model_precision='bf16', codec_device='cuda', codec_precision='bf16'), None),
        ('fp32-gpucodec', dict(model_precision='fp32', codec_device='cuda', codec_precision='fp32'), None),
        ('bf16-gpucodec-steps16', dict(model_precision='bf16', codec_device='cuda', codec_precision='bf16'), 16),
    ]
    for name, key, steps in conds:
        t = time.perf_counter()
        rt = InferenceRuntime.from_key(RuntimeKey(checkpoint=ckpt, model_device='cuda', **key))
        lines.append(f'== {name}: 読み込み {time.perf_counter() - t:.1f} 秒  GPU {torch.cuda.memory_allocated() / 2**30:.2f} GB')
        for warm in (True, False):
            for i, text in enumerate(SENTENCES):
                torch.cuda.synchronize()
                t = time.perf_counter()
                r = rt.synthesize(SamplingRequest(text=text, caption=CAPTION, ref_wavs=refs, num_steps=steps, seed=1), log_fn=None)
                torch.cuda.synchronize()
                dt = time.perf_counter() - t
                dur = r.audio.shape[-1] / r.sample_rate
                if not warm:
                    sf.write(f'{OUT}/{name}-{i}.wav', r.audio.squeeze().float().cpu().numpy(), r.sample_rate)
                    lines.append(f'  文{i}（{len(text)} 字）: 合成 {dt:.2f} 秒 / 音声 {dur:.2f} 秒（実時間比 {dt / dur:.2f}）')
        del rt
        torch.cuda.empty_cache()
    open(f'{OUT}/result.txt', 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    print('BENCH_TTS_DONE')


if __name__ == '__main__':
    main()
