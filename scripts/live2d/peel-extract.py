# -*- coding: utf-8 -*-
"""剥がした段階の絵（消した絵・塗りつぶした絵）から、パーツのレイヤーを取り出す（計画書 8.1）。

段階の定義は JSON（下の例）。段階は上のパーツから順。各パーツの画素は、
  - 元の絵で見えている所（前の段階のパーツに覆われていない所）：元の絵の画素
  - 前の段階のパーツに隠れていた所：その段階の入力の絵の画素（生成した描き足し）
最後の段階の消した絵が、いちばん下の下地になる。重ね直した絵と元の絵の差も出す。

段階の JSON の例
  {"original": "head-1254.png", "base_dir": "assets/ciel/generated/v7/peel",
   "stages": [
     {"input": "head-1254.png", "remove": "nobangs-1.png", "mattes": ["matte-bangs-1.png", "matte-bangs-2.png"],
      "parts": {"Hair_Front": "magenta"}, "strands": ["Hair_Front"]},
     {"input": "nobangs-1.png", "remove": "s1-remove.png", "mattes": ["s1-matte.png"],
      "parts": {"Brow_R": "magenta", "Brow_L": "green"}} ]}
実行  python -I scripts/live2d/peel-extract.py 段階.json 出力フォルダ
出力  <パーツ名>.png（透明）、_base.png（下地）、_recompose.png、_check.png、_report.json
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

COLORS = {  # 塗りつぶしの判定（RGB の大小関係）
    'magenta': lambda c: (c[..., 0] - c[..., 1] > 90) & (c[..., 2] - c[..., 1] > 90),
    'green': lambda c: (c[..., 1] - c[..., 0] > 90) & (c[..., 1] - c[..., 2] > 90),
    # 口・鼻のような細い塗りは、縁が肌の色と混ざるので、ゆるく判定する
    'yellow': lambda c: (c[..., 0] > 200) & (c[..., 1] > 200) & (c[..., 0] - c[..., 2] > 80) & (c[..., 1] - c[..., 2] > 80),
    'orange': lambda c: (c[..., 0] > 200) & (c[..., 0] - c[..., 1] > 40) & (c[..., 1] - c[..., 2] > 40),
}


def rgb(path, size):
    im = Image.open(path).convert('RGBA')
    bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    im = bg.convert('RGB')
    if im.size != size:
        im = im.resize(size, Image.LANCZOS)
    return np.asarray(im).astype(np.float32)


def close(mask, k=5):
    im = Image.fromarray((mask * 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.MaxFilter(k)).filter(ImageFilter.MinFilter(k))) > 127


def soft(mask, r=1.0):
    return np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(r))).astype(np.float32) / 255


def main():
    spec_p, out = sys.argv[1:3]
    spec = json.load(open(spec_p, encoding='utf-8'))
    d = spec['base_dir']
    os.makedirs(out, exist_ok=True)
    orig_im = Image.open(os.path.join(d, spec['original']))
    size = orig_im.size
    orig = rgb(os.path.join(d, spec['original']), size)
    covered = np.zeros(size[::-1], bool)          # これまでのパーツが覆っている所（元の絵で）
    layers = []
    report = []
    for st in spec['stages']:
        inp = rgb(os.path.join(d, st['input']), size)
        rem = rgb(os.path.join(d, st['remove']), size)
        mats = [rgb(os.path.join(d, m), size) for m in st['mattes']]
        # 入力と消した絵の、変わっていない所の差（消した絵の忠実さ）
        stage_masks = {}
        for name, col in st['parts'].items():
            m = np.zeros(size[::-1], bool)
            for mt in mats:
                m |= COLORS[col](mt)
            if name in st.get('strands', []):
                near = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(61))) > 0
                diff = np.abs(inp - rem).sum(-1)
                sat = inp.max(-1) - inp.min(-1)
                m |= (diff > 30) & near & (sat < 60) & (inp.mean(-1) >= 120)
            stage_masks[name] = close(m)
        allm = np.zeros(size[::-1], bool)
        for m in stage_masks.values():
            allm |= m
        un = ~close(allm, 15)
        rms = float(np.sqrt(np.mean(((inp - rem) ** 2)[un])))
        for name, m in stage_masks.items():
            a = soft(m)
            src = np.where(covered[..., None], inp, orig)
            layers.append((name, a))
            Image.fromarray(np.concatenate([src, a[..., None] * 255], -1).astype(np.uint8), 'RGBA').save(os.path.join(out, name + '.png'))
            report.append(dict(stage=st['remove'], part=name, area=float(m.mean()), rms_unchanged_stage=rms))
        covered |= allm
        base = rem
    Image.fromarray(base.astype(np.uint8)).save(os.path.join(out, '_base.png'))
    # 重ね直し：下地の上に、下のパーツから順に（段階の逆順）
    rec = base.copy()
    for name, a in reversed(layers):
        lay = np.asarray(Image.open(os.path.join(out, name + '.png')).convert('RGBA')).astype(np.float32)
        al = lay[..., 3:4] / 255
        rec = rec * (1 - al) + lay[..., :3] * al
    Image.fromarray(np.clip(rec, 0, 255).astype(np.uint8)).save(os.path.join(out, '_recompose.png'))
    rms_all = float(np.sqrt(np.mean((rec - orig) ** 2)))
    sheet = np.concatenate([orig, rec, np.clip(np.abs(rec - orig) * 4, 0, 255), base], 1)
    Image.fromarray(sheet.astype(np.uint8)).resize((sheet.shape[1] // 2, sheet.shape[0] // 2), Image.LANCZOS).save(os.path.join(out, '_check.png'))
    json.dump(dict(rms_recompose=rms_all, parts=report), open(os.path.join(out, '_report.json'), 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    for r in report:
        print('%-14s area=%.3f stage_rms=%.2f' % (r['part'], r['area'], r['rms_unchanged_stage']))
    print('PEEL_EXTRACT_DONE rms_recompose=%.2f' % rms_all)


if __name__ == '__main__':
    main()
