import numpy as np
from PIL import Image, ImageFilter
r = 'D:/CIEL/apps/ciel-companion/assets/ciel/'
a = Image.open(r + 'generated/edit-d-hair-removed.png').convert('RGB').resize((1536, 1536), Image.LANCZOS)
m = Image.open(r + 'requests/face-hair-crop-1536x1536_x318_y236.png').convert('RGB')
A = np.asarray(a).astype(int)
M = np.asarray(m).astype(float)
d = A[..., 2] - A[..., 0]
cand = d <= 1

# 鼻の位置から連結成分（4近傍）を広げる
H, W = cand.shape
seen = np.zeros((H, W), bool)
stack = [(925, 780)]
seen[925, 780] = True
while stack:
    y, x = stack.pop()
    for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
        if 0 <= ny < H and 0 <= nx < W and cand[ny, nx] and not seen[ny, nx]:
            seen[ny, nx] = True
            stack.append((ny, nx))
# 穴（目・口・額の弧）を埋める：外側から背景を広げ、届かない所を内部とする
inv = ~seen
bg = np.zeros((H, W), bool)
stack = [(0, 0)]
bg[0, 0] = True
while stack:
    y, x = stack.pop()
    for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
        if 0 <= ny < H and 0 <= nx < W and inv[ny, nx] and not bg[ny, nx]:
            bg[ny, nx] = True
            stack.append((ny, nx))
face = ~bg
Image.fromarray((face * 255).astype('uint8')).save(r + '../private/ciel/unused-generated/face-mask-check.png') if False else None

# 額の細い弧：顔の内側で、肌より暗い画素を肌色で塗る
band = np.zeros((H, W), bool)
band[480:660, 380:1160] = True
gray = A.mean(2)
arcs = face & band & (gray < 246)
arcs_img = Image.fromarray((arcs * 255).astype('uint8')).filter(ImageFilter.MaxFilter(13))
arcs = np.asarray(arcs_img) > 0
A2 = A.copy().astype(float)
A2[arcs & face] = np.array([252, 250, 250])

# 目は元の画像を使う（目の箱の内側は置き換えない）
keep = np.zeros((H, W), bool)
keep[712:925, 430:745] = True
keep[705:925, 880:1150] = True
rep = face & ~keep
alpha = Image.fromarray((rep * 255).astype('uint8')).filter(ImageFilter.GaussianBlur(3))
al = (np.asarray(alpha).astype(float) / 255)[..., None]
out = M * (1 - al) + A2 * al
res = Image.fromarray(np.clip(out, 0, 255).astype('uint8'))
res.save(r + 'requests/face-hair-draft-1536x1536_x318_y236.png')
print('face px', int(face.sum()))
