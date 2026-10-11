# -*- coding: utf-8 -*-
"""剥がした段階の絵（頭の切り抜き・上半身全体の 2 系統）から、作業キャンバス（2172×2896）上のパーツのレイヤーを作る（計画書 8.1）。

各パーツの画素：
  - 元の絵で見えている所（その系統で前の段階のパーツに覆われていない所）：2 倍の基準画像の画素と透明度
  - 前の段階のパーツに隠れていた所：その段階の入力の絵（生成した描き足し）を、キャンバスの大きさへ拡大した画素
塗りつぶしの範囲は、系統の画像の大きさで求め、キャンバスへ拡大してなめらかにする。
いちばん下の下地（後ろ髪）は、上半身全体の系統の最後の消した絵。

実行  python -I scripts/live2d/peel-assemble.py 設定.json 出力フォルダ
設定  {"master": "assets/ciel/master/ciel-upper-body-2x.png",
       "chains": [{"dir": ..., "original": ..., "box": [x0, y0, x1, y1](キャンバス上の範囲), "use": [使うパーツ名],
                   "stages": [{"input", "remove", "mattes", "parts": {名前: 色}, "strands": [...]}]}],
       "base": {"chain": 1, "image": "f9-remove.png"},
       "order": [下から上へのパーツ名]}
出力  <パーツ名>.png、Hair_Back.png（下地）、_compose.png（重ね直し）、_check.png（元の絵と並べた図）、_report.json
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import importlib.util

spec_ = importlib.util.spec_from_file_location('peel_extract', os.path.join(HERE, 'peel-extract.py'))
pe = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(pe)

W, H = 2172, 2896


def to_canvas_gray(arr, box):
    """系統の画像の大きさの 0〜1 の配列を、キャンバスの box へ拡大して置く。"""
    x0, y0, x1, y1 = box
    im = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8)).resize((x1 - x0, y1 - y0), Image.BILINEAR)
    out = np.zeros((H, W), np.float32)
    out[y0:y1, x0:x1] = np.asarray(im).astype(np.float32) / 255
    return out


def to_canvas_rgb(arr, box):
    x0, y0, x1, y1 = box
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).resize((x1 - x0, y1 - y0), Image.LANCZOS)
    out = np.full((H, W, 3), 255, np.float32)
    out[y0:y1, x0:x1] = np.asarray(im).astype(np.float32)
    return out


def main():
    cfg_p, out = sys.argv[1:3]
    cfg = json.load(open(cfg_p, encoding='utf-8'))
    os.makedirs(out, exist_ok=True)
    master = np.asarray(Image.open(cfg['master']).convert('RGBA')).astype(np.float32)
    m_rgb, m_a = master[..., :3], master[..., 3] / 255
    parts = {}
    report = []
    for ci, ch in enumerate(cfg['chains']):
        d = ch['dir']
        size = Image.open(os.path.join(d, ch['original'])).size
        covered = np.zeros(size[::-1], bool)
        for st in ch['stages']:
            inp = pe.rgb(os.path.join(d, st['input']), size)
            rem = pe.rgb(os.path.join(d, st['remove']), size)
            mats = [pe.rgb(os.path.join(d, m), size) for m in st['mattes']]
            masks = {}
            for name, col in st['parts'].items():
                m = np.zeros(size[::-1], bool)
                for mt in mats:
                    m |= pe.COLORS[col](mt)
                if name in st.get('strands', []):
                    near = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(61))) > 0
                    diff = np.abs(inp - rem).sum(-1)
                    sat = inp.max(-1) - inp.min(-1)
                    m |= (diff > 30) & near & (sat < 60) & (inp.mean(-1) >= 120)
                masks[name] = pe.close(m)
            for name, m in masks.items():
                if name not in ch['use']:
                    continue
                a = to_canvas_gray(pe.soft(m, 0.8), ch['box'])
                cov = to_canvas_gray(covered.astype(np.float32), ch['box']) > 0.5
                fill = to_canvas_rgb(inp, ch['box'])
                rgb = np.where(cov[..., None], fill, m_rgb)
                alpha = np.where(cov, a, a * m_a)
                parts[name] = (rgb, alpha)
                report.append(dict(chain=ci, part=name, area=float(alpha.mean())))
            for m in masks.values():
                covered |= m
        ch['_covered'] = covered
    # 下地（後ろ髪）：最後の消した絵。背景の白（外周につながる、ほぼ白の所）は透明にする
    bc = cfg['chains'][cfg['base']['chain']]
    size = Image.open(os.path.join(bc['dir'], bc['original'])).size
    b = pe.rgb(os.path.join(bc['dir'], cfg['base']['image']), size)
    white = (b.min(-1) > 246)
    # 外周から白い所を塗り広げる
    bg = np.zeros_like(white)
    bg[0, :] = white[0, :]; bg[-1, :] = white[-1, :]; bg[:, 0] = white[:, 0]; bg[:, -1] = white[:, -1]
    for _ in range(400):
        p = np.pad(bg, 1)
        nb = (p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]) & white
        if np.array_equal(nb, bg):
            break
        bg = nb
    ba = to_canvas_gray(pe.soft(~bg, 1.0), bc['box'])
    # 見えている所（どのパーツにも覆われていない所）は、元の絵の画素と透明度
    cov = to_canvas_gray(pe.soft(bc['_covered'], 1.0), bc['box'])
    brgb = to_canvas_rgb(b, bc['box']) * cov[..., None] + m_rgb * (1 - cov[..., None])
    parts['Hair_Back'] = (brgb, ba * cov + m_a * (1 - cov))
    # 書き出しと重ね直し
    comp = np.zeros((H, W, 3), np.float32) + np.array([64, 72, 104], np.float32)
    for name in cfg['order']:
        if name not in parts:
            print('MISSING', name)
            continue
        rgb, a = parts[name]
        Image.fromarray(np.concatenate([rgb, a[..., None] * 255], -1).clip(0, 255).astype(np.uint8), 'RGBA').save(os.path.join(out, name + '.png'))
        comp = comp * (1 - a[..., None]) + rgb * a[..., None]
    orig = np.zeros((H, W, 3), np.float32) + np.array([64, 72, 104], np.float32)
    orig = orig * (1 - m_a[..., None]) + m_rgb * m_a[..., None]
    rms = float(np.sqrt(np.mean((comp - orig) ** 2)))
    Image.fromarray(comp.astype(np.uint8)).save(os.path.join(out, '_compose.png'))
    sheet = np.concatenate([orig, comp, np.clip(np.abs(comp - orig) * 4, 0, 255)], 1)
    Image.fromarray(sheet.astype(np.uint8)).resize((sheet.shape[1] // 3, sheet.shape[0] // 3), Image.LANCZOS).save(os.path.join(out, '_check.png'))
    json.dump(dict(rms_compose=rms, parts=report), open(os.path.join(out, '_report.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print('PEEL_ASSEMBLE_DONE parts=%d rms=%.2f' % (len(parts), rms))


if __name__ == '__main__':
    main()
