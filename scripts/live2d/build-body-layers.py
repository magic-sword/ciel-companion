"""体の下地と、衣装のレイヤーを作る。

入力  assets/ciel/master/ciel-upper-body-2x.png    基準画像
      assets/ciel/generated/edit-f-body-bare.png   依頼F（衣装を消した体。切り抜き body-crop の部分編集）
出力  assets/ciel/layers/body/Body_Base.png（Fの画像を基準画像の大きさへ拡大した下地：素の体・後ろ髪・トップス・スカート）
      assets/ciel/layers/body/{Neck_Gear,Chest_Gem,Waist_Belt,Outer_R,Outer_L}.png
      （基準画像の画素のうち、Fで消えた所＝首輪と飾り・胸の宝石・腰のベルト・ファーとジャケットと袖）、check-body.png
実行  python -I scripts/live2d/build-body-layers.py   完了表示 BODY_LAYERS_READY
重ね順 Body_Base < Outer_* < Waist_Belt < Chest_Gem < Neck_Gear

考え方：Fは切り抜き（基準画像の x0・y1267、2172×1629）の2/3の大きさで、倍率1.5・ずれ0で重なる。
元とFの差が大きい所を衣装とする。細い線のずれによる差は、開く処理で除く。トップスとスカートはFにも残っているので下地に含まれる。
"""
import os

import numpy as np
from PIL import Image, ImageFilter

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'assets', 'ciel')
X, Y, CW, CH = 0, 1267, 2172, 1629
THRESHOLD = 35
# 衣装の種類の目安（切り抜き内の座標 x0, y0, x1, y1）
NECK_GEAR = (860, 60, 1340, 440)     # 首輪と飾り
CHEST_GEM = (990, 440, 1250, 680)    # 胸の宝石
WAIST_BELT = (820, 1100, 1420, 1220) # 腰のベルト
MID_X = 1086                         # Outer の左右の境（画面の左が R）
FUR_ZONES = [(120, 120, 800, 800), (1370, 120, 2050, 800)]   # 左右の肩のファー（切り抜き内）。ここだけ大きく閉じる


def morph(m, size, grow):
    f = ImageFilter.MaxFilter if grow else ImageFilter.MinFilter
    return np.asarray(Image.fromarray((m * 255).astype('uint8')).filter(f(size))) > 0


def blur(m, r):
    return np.asarray(Image.fromarray((m * 255).astype('uint8')).filter(ImageFilter.GaussianBlur(r))).astype(float) / 255


def drop_small(mask, min_px):
    h, w = mask.shape
    seen = np.zeros((h, w), bool)
    out = mask.copy()
    for sy, sx in zip(*np.nonzero(mask)):
        if seen[sy, sx]:
            continue
        comp = [(sy, sx)]
        seen[sy, sx] = True
        i = 0
        while i < len(comp):
            y, x = comp[i]
            i += 1
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    comp.append((ny, nx))
        if len(comp) < min_px:
            for y, x in comp:
                out[y, x] = False
    return out


master = Image.open(os.path.join(ROOT, 'master', 'ciel-upper-body-2x.png')).convert('RGBA')
MW, MH = master.size
Mfull = np.asarray(master).astype(float)
crop = master.crop((X, Y, X + CW, Y + CH))
bg = Image.new('RGBA', crop.size, (255, 255, 255, 255))
bg.alpha_composite(crop)
B = np.asarray(bg.convert('RGB')).astype(float)
F = np.asarray(Image.open(os.path.join(ROOT, 'generated', 'edit-f-body-bare.png')).convert('RGB')
               .resize((CW, CH), Image.LANCZOS)).astype(float)

diff = np.abs(F - B).sum(2)
diff = np.asarray(Image.fromarray(np.clip(diff, 0, 255).astype('uint8')).filter(ImageFilter.GaussianBlur(2))).astype(float)
cloth = diff > THRESHOLD
cloth = morph(morph(cloth, 9, False), 9, True)     # 開く：細い線のずれを除く


def big_close(mask, radius):
    # 1/4の大きさで閉じる処理（ファーの内側は髪と同じ白で差が出ず、大きな穴になる）。元の範囲の外へ radius px を超えて広げない
    small = Image.fromarray((mask * 255).astype('uint8')).resize((CW // 4, CH // 4), Image.BILINEAR)
    k = radius // 4 * 2 + 1
    closed = small.filter(ImageFilter.MaxFilter(k)).filter(ImageFilter.MinFilter(k))
    up = np.asarray(closed.resize((CW, CH), Image.BILINEAR)) > 127
    zone = np.zeros(mask.shape, bool)
    for x0, y0, x1, y1 in FUR_ZONES:
        zone[y0:y1, x0:x1] = True
    return (up & zone) | mask


cloth = morph(morph(cloth, 61, True), 61, False)   # 閉じる：細かい隙間をつなぐ
cloth = big_close(cloth, 200)                      # 閉じる：ファーの内側の大きな穴をつなぐ
cloth = drop_small(cloth, 3000)


def fill_holes(mask):
    # 外側から塗り広げ、届かない所（衣装に囲まれた穴）を衣装に含める
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


cloth = fill_holes(cloth)
cloth = morph(cloth, 3, True)


def box_mask(box):
    m = np.zeros(cloth.shape, bool)
    x0, y0, x1, y1 = box
    m[y0:y1, x0:x1] = True
    return m


neck = cloth & box_mask(NECK_GEAR)
gem = cloth & box_mask(CHEST_GEM) & ~neck
belt = cloth & box_mask(WAIST_BELT) & ~neck & ~gem
rest = cloth & ~neck & ~gem & ~belt
xs = np.arange(CW)[None, :].repeat(CH, 0)
parts = {'Neck_Gear': neck, 'Chest_Gem': gem, 'Waist_Belt': belt,
         'Outer_R': rest & (xs < MID_X), 'Outer_L': rest & (xs >= MID_X)}

out_dir = os.path.join(ROOT, 'layers', 'body')
os.makedirs(out_dir, exist_ok=True)


def save_full(rgb, alpha, name):
    layer = np.zeros((MH, MW, 4), np.uint8)
    layer[Y:Y + CH, X:X + CW, :3] = np.clip(rgb, 0, 255).astype('uint8')
    layer[Y:Y + CH, X:X + CW, 3] = np.clip(alpha * 255, 0, 255).astype('uint8')
    Image.fromarray(layer, 'RGBA').save(os.path.join(out_dir, name))


# 下地：Fの画像。基準画像の不透明な範囲（髪の外形）より外は透明にする。F で描き足された後ろ髪の範囲も含める。
f_nonwhite = (255 - F.min(2)) >= 4
base_alpha = np.maximum(Mfull[Y:Y + CH, X:X + CW, 3] / 255, blur(morph(f_nonwhite, 3, True), 1.0))
save_full(F, base_alpha, 'Body_Base.png')

comp = F * base_alpha[..., None] + 255 * (1 - base_alpha[..., None])
mw = Mfull[Y:Y + CH, X:X + CW, 3] / 255
for name, mask in parts.items():
    a = blur(mask, 1.5) * mw
    save_full(B, a, name + '.png')
for name in ('Outer_R', 'Outer_L', 'Waist_Belt', 'Chest_Gem', 'Neck_Gear'):
    a = (blur(parts[name], 1.5) * mw)[..., None]
    comp = comp * (1 - a) + B * a
ref = B
region_rms = float(np.sqrt(((comp - ref) ** 2)[(diff > THRESHOLD)].mean()))
all_rms = float(np.sqrt(((comp - ref) ** 2).mean()))
view = np.concatenate([ref, comp], 1)
Image.fromarray(np.clip(view, 0, 255).astype('uint8')).resize((CW, CH // 2), Image.LANCZOS).save(os.path.join(out_dir, 'check-body.png'))
print('BODY_LAYERS_READY cloth_px=%d rms_all=%.2f rms_changed=%.2f' % (cloth.sum(), all_rms, region_rms))
