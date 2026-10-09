"""顔の肌と前髪・横髪のレイヤーを作る。

入力  assets/ciel/master/ciel-upper-body-2x.png       基準画像
      assets/ciel/master/ciel-upper-body-2x-eyeless.png 目のない顔
      assets/ciel/generated/edits/edit-d-hair-removed.png     依頼D（前髪を消した顔。画像全体が描き直されているので、顔の肌の領域だけを使う）
出力  assets/ciel/layers/head/{Face_Skin,Hair_Front}.png（基準画像と同じキャンバス）、check-head.png
実行  python -I scripts/live2d/build-head-layers.py   完了表示 HEAD_LAYERS_READY
重ね順 目のない顔 < Face_Skin < 目 < Hair_Front

考え方
- 顔の肌の領域 F：依頼Dの画像（倍率1.225）で、肌は髪より青−赤が小さい。鼻から塗り広げ、穴（目・口）を埋める。
- 見えている肌 V：基準画像で、輪郭線を壁にして鼻から塗り広げる。
- Face_Skin：V は基準画像の肌、髪に隠れていた所（F−V）は依頼Dの肌。目の箱は目のない顔。
- Hair_Front：F の内側で、V と目の箱を除いた所の基準画像の画素（髪に隠れていた肌の上に重なる前髪・横髪）。
"""
import os

import numpy as np
from PIL import Image, ImageFilter

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'assets', 'ciel')
X, Y, W = 318, 236, 1536          # 依頼Dの切り抜きの位置と大きさ（基準画像の座標）
NOSE = (925, 780)                 # 切り抜き内の鼻の位置 (y, x)
NECK_Y = 1105                     # これより下（首輪）は顔の肌に含めない
SKIN = np.array([252, 250, 250], float)


def flood(allowed, start):
    h, w = allowed.shape
    seen = np.zeros((h, w), bool)
    seen[start] = True
    stack = [start]
    while stack:
        y, x = stack.pop()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and allowed[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                stack.append((ny, nx))
    return seen


def fill_holes(mask):
    outside = flood(~mask, (0, 0))
    return ~outside


def morph(mask, size, grow):
    im = Image.fromarray((mask * 255).astype('uint8'))
    f = ImageFilter.MaxFilter if grow else ImageFilter.MinFilter
    return np.asarray(im.filter(f(size))) > 0


def blur(mask, r):
    im = Image.fromarray((mask * 255).astype('uint8')).filter(ImageFilter.GaussianBlur(r))
    return np.asarray(im).astype(float) / 255


def flat(img):
    bg = Image.new('RGBA', img.size, (255, 255, 255, 255))
    bg.alpha_composite(img)
    return np.asarray(bg.convert('RGB')).astype(float)


master = Image.open(os.path.join(ROOT, 'master', 'ciel-upper-body-2x.png')).convert('RGBA')
eyeless = Image.open(os.path.join(ROOT, 'master', 'ciel-upper-body-2x-eyeless.png')).convert('RGBA')
crop = (X, Y, X + W, Y + W)
M = flat(master.crop(crop))
E = flat(eyeless.crop(crop))
D = np.asarray(Image.open(os.path.join(ROOT, 'generated', 'edits', 'edit-d-hair-removed.png')).convert('RGB')
               .resize((W, W), Image.LANCZOS)).astype(float)

# F：依頼Dの顔の肌の領域
dchroma = D[..., 2] - D[..., 0]
F = fill_holes(flood(dchroma <= 1, NOSE))
F[NECK_Y:, :] = False

# 額の細い弧（依頼Dの消し残し）を肌色にする
band = np.zeros(F.shape, bool)
band[480:660, 380:1160] = True
arcs = morph(F & band & (D.mean(2) < 246), 13, True)
D = D.copy()
D[arcs & F] = SKIN

# V：基準画像で見えている肌（輪郭線を壁に塗り広げる）
g = np.asarray(Image.fromarray(M.mean(2).astype('uint8')).filter(ImageFilter.GaussianBlur(1.2))).astype(float)
gy, gx = np.gradient(g)
barrier = morph(np.hypot(gx, gy) > 1.6, 5, True)
V = flood(~barrier, NOSE)
V = morph(morph(V, 7, True), 7, False)       # 小さな穴を閉じる

# 目の範囲：目のレイヤー（build-eye-layers.ps1の出力）の形を少し広げたもの
eyebox = np.zeros(F.shape, bool)
for side in ('R', 'L'):
    for part in ('sclera', 'iris', 'lash', 'crease'):
        a = np.asarray(Image.open(os.path.join(ROOT, 'layers', 'eyes', '%s_%s.png' % (side, part))).convert('RGBA'))[Y:Y + W, X:X + W, 3]
        eyebox |= a > 8
eyebox = morph(eyebox, 9, True)

skin_area = F | V
Vb = morph(V, 19, True)
vw = blur(Vb, 6)[..., None]          # V の中は基準画像の肌へ、外は依頼Dの肌へなだらかにつなぐ
skin_rgb = M * vw + D * (1 - vw)
ew = blur(eyebox, 4)[..., None]
skin_rgb = E * ew + skin_rgb * (1 - ew)               # 目の箱は目のない顔の肌
skin_a = blur(skin_area | eyebox, 1.5)

hair_area = F & ~Vb & ~eyebox
hair_a = blur(morph(hair_area, 5, True) & ~Vb & ~eyebox, 1.2)

out_dir = os.path.join(ROOT, 'layers', 'head')
os.makedirs(out_dir, exist_ok=True)
size = master.size


def put(rgb, a, name):
    layer = np.zeros((size[1], size[0], 4), np.uint8)
    layer[Y:Y + W, X:X + W, :3] = np.clip(rgb, 0, 255).astype('uint8')
    layer[Y:Y + W, X:X + W, 3] = np.clip(a * 255, 0, 255).astype('uint8')
    Image.fromarray(layer, 'RGBA').save(os.path.join(out_dir, name))


put(skin_rgb, skin_a, 'Face_Skin.png')
put(M, hair_a, 'Hair_Front.png')

# 確認：目のない顔 < Face_Skin < 通常の目（ここでは基準画像の目の箱）< Hair_Front と基準画像の差
base = E.copy()
comp = base * (1 - skin_a[..., None]) + skin_rgb * skin_a[..., None]
comp = comp * (1 - ew * 0)
eyes = np.where(eyebox[..., None], M, comp)
comp = eyes * (1 - hair_a[..., None]) + M * hair_a[..., None]
rms_face = float(np.sqrt(((comp - M) ** 2)[F].mean()))
diff = np.clip(np.abs(comp - M).sum(2) * 4, 0, 255).astype('uint8')
check = Image.new('RGB', (W * 3 // 2, W // 2))
for i, im in enumerate((M, comp, np.stack([diff] * 3, 2))):
    check.paste(Image.fromarray(np.clip(im, 0, 255).astype('uint8')).resize((W // 2, W // 2), Image.LANCZOS), (i * W // 2, 0))
check.save(os.path.join(out_dir, 'check-head.png'))
print('HEAD_LAYERS_READY face_rms=%.2f F=%d V=%d hair=%d' % (rms_face, F.sum(), V.sum(), hair_area.sum()))
