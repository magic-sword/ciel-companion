"""口（閉じ・小・大）と後ろ髪のレイヤーを作る。

入力  assets/ciel/requests/face-hair-crop-1536x1536_x318_y236.png  切り抜き（基準画像の x318・y236）
      assets/ciel/generated/G1_Closed.png / G2_Small_Open.png / G3_Large_Open.png
          依頼G。切り抜きの口だけを描き直した部分編集（口以外の差は 0）
      assets/ciel/generated/ciel-rear-hair-layer-1536.png  後ろ髪だけの透明PNG（切り抜きと同じ大きさ・位置）
出力  assets/ciel/layers/head/{Mouth_Closed,Mouth_Small,Mouth_Large,Hair_Back}.png（基準画像と同じキャンバス）
      assets/ciel/layers/head/check-mouth-hair.png
実行  python -I scripts/live2d/build-mouth-and-hair-layers.py   完了表示 MOUTH_HAIR_LAYERS_READY

考え方
- 口：G1〜G3 と切り抜きの差が出る範囲が口。差の範囲に少し余白を足し、G の画素をそのまま使う（口の周りの肌は
  切り抜きと同じなので、重ねても継ぎ目が出ない）。G1 は切り抜きと同一（口が閉じた笑顔）なので、閉じた口の線は
  切り抜きから切り出す。切り出す範囲は G2・G3 の口が開く範囲を含める。
- 後ろ髪：透明PNGをそのまま、基準画像の座標へ置く。
"""
import os

import numpy as np
from PIL import Image, ImageFilter

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'assets', 'ciel')
X, Y, W = 318, 236, 1536
MARGIN = 14


def load_rgb(path):
    im = Image.open(os.path.join(ROOT, path)).convert('RGBA')
    bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return np.asarray(bg.convert('RGB')).astype(float)


def blur(mask, r):
    return np.asarray(Image.fromarray((mask * 255).astype('uint8')).filter(ImageFilter.GaussianBlur(r))).astype(float) / 255


def grow(mask, size):
    return np.asarray(Image.fromarray((mask * 255).astype('uint8')).filter(ImageFilter.MaxFilter(size))) > 0


master = Image.open(os.path.join(ROOT, 'master', 'ciel-upper-body-2x.png'))
MW, MH = master.size
base = load_rgb('requests/face-hair-crop-1536x1536_x318_y236.png')
samples = {
    'Mouth_Closed': load_rgb('generated/G1_Closed.png'),
    'Mouth_Small': load_rgb('generated/G2_Small_Open.png'),
    'Mouth_Large': load_rgb('generated/G3_Large_Open.png'),
}

# 口の範囲：G2・G3 のどちらかで切り抜きと差が出る所（G1 は切り抜きと同一）。
changed = np.zeros((W, W), bool)
for key in ('Mouth_Small', 'Mouth_Large'):
    changed |= np.abs(samples[key] - base).sum(2) > 6
ys, xs = np.nonzero(changed)
x0, x1, y0, y1 = xs.min() - MARGIN, xs.max() + MARGIN, ys.min() - MARGIN, ys.max() + MARGIN
box = np.zeros((W, W), bool)
box[y0:y1 + 1, x0:x1 + 1] = True
print('mouth box x %d-%d y %d-%d' % (x0, x1, y0, y1))

out_dir = os.path.join(ROOT, 'layers', 'head')
os.makedirs(out_dir, exist_ok=True)


def put(rgb, alpha, name):
    layer = np.zeros((MH, MW, 4), np.uint8)
    layer[Y:Y + W, X:X + W, :3] = np.clip(rgb, 0, 255).astype('uint8')
    layer[Y:Y + W, X:X + W, 3] = np.clip(alpha * 255, 0, 255).astype('uint8')
    Image.fromarray(layer, 'RGBA').save(os.path.join(out_dir, name))


alpha = blur(box, 3)
for key, img in samples.items():
    put(img, alpha, key + '.png')

# 後ろ髪（透明PNG）
rear = Image.open(os.path.join(ROOT, 'generated', 'ciel-rear-hair-layer-1536.png')).convert('RGBA')
assert rear.size == (W, W), rear.size
layer = Image.new('RGBA', (MW, MH), (0, 0, 0, 0))
layer.paste(rear, (X, Y))
layer.save(os.path.join(out_dir, 'Hair_Back.png'))

# 確認：口3種を、切り抜きの上に重ねた結果と、後ろ髪
tiles = []
for key, img in samples.items():
    comp = base * (1 - alpha[..., None]) + img * alpha[..., None]
    tiles.append(Image.fromarray(np.clip(comp, 0, 255).astype('uint8')).crop((520, 880, 1100, 1200)))
rear_bg = Image.new('RGBA', rear.size, (70, 70, 100, 255))
rear_bg.alpha_composite(rear)
o = Image.new('RGB', (580 * 3, 320 + 400), (255, 255, 255))
for i, t in enumerate(tiles):
    o.paste(t, (i * 580, 0))
o.paste(rear_bg.convert('RGB').resize((400, 400)), (0, 320))
o.save(os.path.join(out_dir, 'check-mouth-hair.png'))
print('MOUTH_HAIR_LAYERS_READY')
