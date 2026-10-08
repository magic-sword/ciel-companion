"""耳のレイヤーと、耳の下の髪を作る。

入力  assets/ciel/master/ciel-upper-body-2x.png     基準画像
      assets/ciel/generated/edit-e-ears-removed.png 依頼E（耳を消した顔。切り抜き face-hair-crop の部分編集）
出力  assets/ciel/layers/head/{Ear_R,Ear_L,Hair_Under_Ear}.png（基準画像と同じキャンバス）、check-ears.png
実行  python -I scripts/live2d/build-ear-layers.py   完了表示 EAR_LAYERS_READY
L/R はキャラクターから見た左右（Ear_R は画面の左）。

考え方
- E は切り抜き（基準画像の x318・y236、1536×1536）の約0.667倍。倍率1.5・ずれ0で重なる（耳以外の差 RMS 1.4）。
- 耳の範囲：切り抜きと E の差が大きい所（上部）。切り抜きの上（y<236）にはみ出す耳の先は、基準画像の不透明な画素のうち、頭の中央（アホ毛）を除いた所。
- Ear_*：耳の範囲の基準画像の画素。Hair_Under_Ear：同じ範囲の E の画素（耳に隠れていた髪）。
"""
import os

import numpy as np
from PIL import Image, ImageFilter

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'assets', 'ciel')
X, Y, W = 318, 236, 1536
THRESHOLD = 28          # 3チャンネルの差の合計（耳以外の差は5前後）
CENTER_L, CENTER_R = 900, 1250   # 基準画像の x。この間は頭の中央（アホ毛）なので耳に含めない


def blur(mask, r):
    return np.asarray(Image.fromarray((mask * 255).astype('uint8')).filter(ImageFilter.GaussianBlur(r))).astype(float) / 255


def morph(mask, size, grow):
    f = ImageFilter.MaxFilter if grow else ImageFilter.MinFilter
    return np.asarray(Image.fromarray((mask * 255).astype('uint8')).filter(f(size))) > 0


master = Image.open(os.path.join(ROOT, 'master', 'ciel-upper-body-2x.png')).convert('RGBA')
MW, MH = master.size
mid_x = (CENTER_L + CENTER_R) // 2
M = np.asarray(master).astype(float)
crop_bg = Image.new('RGBA', (W, W), (255, 255, 255, 255))
crop_bg.alpha_composite(master.crop((X, Y, X + W, Y + W)))
B = np.asarray(crop_bg.convert('RGB')).astype(float)
E = np.asarray(Image.open(os.path.join(ROOT, 'generated', 'edit-e-ears-removed.png')).convert('RGB')
               .resize((W, W), Image.LANCZOS)).astype(float)

diff = np.abs(E - B).sum(2)
diff = np.asarray(Image.fromarray(np.clip(diff, 0, 255).astype('uint8')).filter(ImageFilter.GaussianBlur(2))).astype(float)
ear_crop = morph(morph(diff > THRESHOLD, 15, True), 15, False)
ear_crop[560:, :] = False                     # 耳は上部だけ
ear_crop = morph(ear_crop, 9, True)

# 耳の範囲を基準画像の全体へ置く
ear = np.zeros((MH, MW), bool)
ear[Y:Y + W, X:X + W] = ear_crop
above = np.zeros((MH, MW), bool)
above[:Y, :] = M[:Y, :, 3] > 8
above[:, CENTER_L:CENTER_R] = False
ear |= above
ear = morph(ear, 5, True)


def fill_holes(mask):
    # 外側から塗り広げ、届かない所（耳の内側の白い毛など。Eの髪と同じ白で差が出ない）を耳に含める
    h, w = mask.shape
    outside = np.zeros((h, w), bool)
    outside[0, 0] = True
    stack = [(0, 0)]
    while stack:
        y, x = stack.pop()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and not mask[ny, nx] and not outside[ny, nx]:
                outside[ny, nx] = True
                stack.append((ny, nx))
    return ~outside


top = Y + 620
left_part = ear[:top, :mid_x]
right_part = ear[:top, mid_x:]
ear[:top, :mid_x] = fill_holes(left_part)
ear[:top, mid_x:] = fill_holes(right_part)
# 耳の内側の穴は、基準画像で不透明な所だけ（背景の穴を埋めない）
ear &= (M[..., 3] > 8)

xs = np.arange(MW)[None, :].repeat(MH, 0)
mid = (CENTER_L + CENTER_R) // 2
out_dir = os.path.join(ROOT, 'layers', 'head')
os.makedirs(out_dir, exist_ok=True)


def save(rgb, a, name):
    layer = np.zeros((MH, MW, 4), np.uint8)
    layer[..., :3] = np.clip(rgb, 0, 255).astype('uint8')
    layer[..., 3] = np.clip(a * 255, 0, 255).astype('uint8')
    Image.fromarray(layer, 'RGBA').save(os.path.join(out_dir, name))


master_alpha = M[..., 3] / 255
for name, side in (('Ear_R.png', xs < mid), ('Ear_L.png', xs >= mid)):
    a = blur(ear & side, 1.2) * master_alpha
    save(M[..., :3], a, name)

# 耳の下の髪：Eの画素（耳の範囲の内側）。切り抜きの外は元の画像に髪がないので作らない
under = np.zeros((MH, MW, 3))
under[Y:Y + W, X:X + W] = E
under_a = np.zeros((MH, MW))
under_a[Y:Y + W, X:X + W] = blur(ear[Y:Y + W, X:X + W], 1.2)
save(under, under_a, 'Hair_Under_Ear.png')

# 確認：耳なしの下地 + Hair_Under_Ear の上に Ear を重ねた結果と、基準画像の差
bg = np.full((MH, MW, 3), 255.0)
base = bg.copy()
base[Y:Y + W, X:X + W] = E
comp = base * (1 - master_alpha[..., None]) + M[..., :3] * master_alpha[..., None]
ea = np.maximum(blur(ear & (xs < mid), 1.2), blur(ear & (xs >= mid), 1.2))[..., None] * master_alpha[..., None]
comp = comp * (1 - ea) + M[..., :3] * ea
ref = bg * (1 - master_alpha[..., None]) + M[..., :3] * master_alpha[..., None]
region = (np.arange(MH)[:, None] < Y + 600) & (np.arange(MW)[None, :] > 0)
rms = float(np.sqrt(((comp - ref) ** 2)[region].mean()))
view = Image.fromarray(np.clip(np.concatenate([ref[:Y + 700], comp[:Y + 700]], 1), 0, 255).astype('uint8'))
view.resize((view.width // 3, view.height // 3), Image.LANCZOS).save(os.path.join(out_dir, 'check-ears.png'))
print('EAR_LAYERS_READY ear_px=%d rms=%.2f' % (ear.sum(), rms))
