# -*- coding: utf-8 -*-
"""会話画面（A案「シエルの視界」）の UI の画像を作る。

形（丸・六角・輪・光）とアイコンは白一色で作り、色は Unity で付ける（Image.color）。
4 倍の大きさで描いてから縮めて、縁をなめらかにする。
仮の背景は、企画設計の世界観の絵（D:/CIEL/企画設計）を縦長に切り抜き、ぼかしたもの。本番の背景ができたら差し替える。

実行（リポジトリのルートで）：python scripts/ui/make_ui_sprites.py
出力：unity/Assets/Resources/CielUI/ （取り込みの設定は Assets/Editor/CielUIImport.cs）
"""
import math
import os
import sys

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUT = os.path.join(ROOT, 'unity', 'Assets', 'Resources', 'CielUI')
WORLD = os.environ.get('CIEL_WORLD_DIR', 'D:/CIEL/企画設計')
SS = 4   # 描くときの倍率


def canvas(w, h):
    return Image.new('L', (w * SS, h * SS), 0)


def save(mask, name, size=None):
    """mask（白の濃さ）を縮めて、白に透明度をつけた PNG にする。"""
    w, h = size or (mask.width // SS, mask.height // SS)
    a = mask.resize((w, h), Image.LANCZOS)
    img = Image.new('RGBA', (w, h), (255, 255, 255, 0))
    img.putalpha(a)
    os.makedirs(os.path.dirname(os.path.join(OUT, name)), exist_ok=True)
    img.save(os.path.join(OUT, name), optimize=True)


# ---- 形 ----

def circle(n=128):
    m = canvas(n, n)
    ImageDraw.Draw(m).ellipse((0, 0, n * SS - 1, n * SS - 1), fill=255)
    save(m, 'circle.png')


def circle_outline(n=128, stroke=4):
    m = canvas(n, n)
    d = ImageDraw.Draw(m)
    d.ellipse((0, 0, n * SS - 1, n * SS - 1), fill=255)
    s = stroke * SS
    d.ellipse((s, s, n * SS - 1 - s, n * SS - 1 - s), fill=0)
    save(m, 'circle_outline.png')


def ring(n=256, stroke=3.0, name='ring.png', dash=None):
    """輪。dash=(点の長さ、間の長さ)（度）なら点線"""
    m = canvas(n, n)
    d = ImageDraw.Draw(m)
    c = n * SS / 2
    r = c - stroke * SS
    w = max(1, round(stroke * SS))
    if dash is None:
        d.ellipse((c - r - w / 2, c - r - w / 2, c + r + w / 2, c + r + w / 2), outline=255, width=w)
    else:
        on, off = dash
        a = 0.0
        while a < 360:
            p = arc_points(c, c, r, a, a + on, 4)
            stroke_path(d, p, w)
            a += on + off
    save(m, name)


def hexagon_points(w, h, inset=0.0):
    # 尖りが上下の六角（Ciel Prism と同じ向き）
    pts = [(0.5, 0), (1, 0.25), (1, 0.75), (0.5, 1), (0, 0.75), (0, 0.25)]
    cx, cy = w / 2, h / 2
    return [(cx + (x * w - cx) * (1 - inset), cy + (y * h - cy) * (1 - inset)) for x, y in pts]


def hexagon(w=152, h=168):
    m = canvas(w, h)
    ImageDraw.Draw(m).polygon(hexagon_points(w * SS, h * SS), fill=255)
    save(m, 'hex.png')


def hexagon_prism(w=152, h=168):
    """マイクのボタン：Ciel Prism の色（明るいシアン → シアン → 深い青）の六角。これだけは色付き"""
    stops = [(0.0, (0xB8, 0xF6, 0xFF)), (0.45, (0x2C, 0xC8, 0xEE)), (1.0, (0x0A, 0x84, 0xB8))]
    W, H = w * SS, h * SS
    m = canvas(w, h)
    ImageDraw.Draw(m).polygon(hexagon_points(W, H), fill=255)
    img = Image.new('RGB', (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            t = min(1.0, max(0.0, x / w * 0.34 + y / h * 0.94 - 0.14))   # 160 度の向き
            for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
                if t <= t1:
                    u = (t - t0) / (t1 - t0)
                    px[x, y] = tuple(int(a + (b - a) * u) for a, b in zip(c0, c1))
                    break
    img.putalpha(m.resize((w, h), Image.LANCZOS))
    img.save(os.path.join(OUT, 'hex_prism.png'), optimize=True)


def glow(n=256):
    """ぼんやりした光（中心が濃い）"""
    img = Image.new('L', (n, n))
    px = img.load()
    c = (n - 1) / 2
    for y in range(n):
        for x in range(n):
            r = math.hypot(x - c, y - c) / c
            px[x, y] = int(255 * max(0.0, 1 - r) ** 2.2)
    out = Image.new('RGBA', (n, n), (255, 255, 255, 0))
    out.putalpha(img)
    out.save(os.path.join(OUT, 'glow.png'), optimize=True)


def hex_glow(w=152, h=168, pad=48):
    m = Image.new('L', (w + pad * 2, h + pad * 2))
    ImageDraw.Draw(m).polygon([(x + pad, y + pad) for x, y in hexagon_points(w, h)], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(pad / 2.5))
    out = Image.new('RGBA', m.size, (255, 255, 255, 0))
    out.putalpha(m)
    out.save(os.path.join(OUT, 'hex_glow.png'), optimize=True)


def vertical_gradient(h=256):
    """上が透明、下が不透明（画面の下の文字を読みやすくする暗がり）"""
    img = Image.new('L', (4, h))
    px = img.load()
    for y in range(h):
        t = y / (h - 1)
        for x in range(4):
            px[x, y] = int(255 * t ** 1.2)
    out = Image.new('RGBA', (4, h), (255, 255, 255, 0))
    out.putalpha(img)
    out.save(os.path.join(OUT, 'fade.png'), optimize=True)


def corner_arc(n=256):
    """画面の左上の隅の弧（右上は Unity で左右を反転して使う）。左下の端に小さな点。
    モックアップ（390 幅の画面）の左上 128×128 の範囲：(14,120) から (120,14) への半径 300 の弧"""
    m = canvas(n, n)
    d = ImageDraw.Draw(m)
    k = n * SS / 128
    c = 67 + 290.5 / math.sqrt(2)   # 弧の中心（右下の外）
    pts = [(x * k, y * k) for x, y in arc_points(c, c, 300, 210.5, 239.5, 0.25)]
    stroke_path(d, pts, 1.2 * k)
    x0, y0 = pts[0]
    d.ellipse((x0 - 2 * k, y0 - 2 * k, x0 + 2 * k, y0 + 2 * k), fill=255)
    save(m, 'corner_arc.png')


# ---- アイコン（24 の升目で描き、96px で書き出す。線の太さ 1.8） ----

def arc_points(cx, cy, r, a0, a1, step=3):
    n = max(2, int(abs(a1 - a0) / step) + 1)
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / (n - 1))),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / (n - 1)))) for i in range(n)]


def stroke_path(d, pts, w, closed=False):
    if closed:
        pts = list(pts) + [pts[0]]
    for a, b in zip(pts, pts[1:]):
        d.line([a, b], fill=255, width=int(round(w)))
    for x, y in pts:
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=255)


class Icon:
    def __init__(self, name, n=96, width=1.8):
        self.name, self.n = name, n
        self.k = n * SS / 24
        self.w = width * self.k
        self.m = canvas(n, n)
        self.d = ImageDraw.Draw(self.m)

    def p(self, pts):
        return [(x * self.k, y * self.k) for x, y in pts]

    def line(self, *pts, closed=False):
        stroke_path(self.d, self.p(pts), self.w, closed)

    def arc(self, cx, cy, r, a0, a1):
        stroke_path(self.d, self.p(arc_points(cx, cy, r, a0, a1)), self.w)

    def circle(self, cx, cy, r):
        self.arc(cx, cy, r, 0, 360)

    def rrect(self, x, y, w, h, r):
        pts = arc_points(x + w - r, y + r, r, -90, 0) + arc_points(x + w - r, y + h - r, r, 0, 90) \
            + arc_points(x + r, y + h - r, r, 90, 180) + arc_points(x + r, y + r, r, 180, 270)
        stroke_path(self.d, self.p(pts), self.w, closed=True)

    def save(self):
        save(self.m, f'Icons/{self.name}.png')


def icons():
    i = Icon('mic', width=2)
    i.rrect(9, 3, 6, 11, 3)
    i.arc(12, 11, 7, 0, 180)
    i.line((12, 18), (12, 21))
    i.save()

    i = Icon('minutes', width=1.7)
    i.line((7, 3), (14, 3), (18, 7), (18, 21), (7, 21), closed=True)
    i.line((10, 11), (15, 11))
    i.line((10, 15), (15, 15))
    i.save()

    def speaker(i):
        i.line((4, 10), (4, 14), (8, 14), (13, 18), (13, 6), (8, 10), closed=True)

    i = Icon('speaker', width=1.7)
    speaker(i)
    i.arc(16, 12, 3, -90, 90)
    i.arc(16, 12, 6.5, -70, 70)
    i.save()

    i = Icon('speaker_low', width=1.7)
    speaker(i)
    i.save()

    i = Icon('earpiece', width=1.7)   # 受話口：耳に当てる受話器
    i.arc(12, 12, 8, 120, 240)
    i.line((8.0, 5.1), (10.5, 3.6), (12.8, 7.6), (10.4, 9.4))
    i.line((8.0, 18.9), (10.5, 20.4), (12.8, 16.4), (10.4, 14.6))
    i.save()

    i = Icon('settings', width=1.8)
    i.line((4, 7), (14, 7))
    i.line((18, 7), (20, 7))
    i.line((4, 17), (8, 17))
    i.line((12, 17), (20, 17))
    i.circle(16, 7, 2)
    i.circle(10, 17, 2)
    i.save()

    i = Icon('close', width=2)
    i.line((6, 6), (18, 18))
    i.line((18, 6), (6, 18))
    i.save()

    i = Icon('check', width=3)
    i.line((5, 12), (10, 17), (19, 7))
    i.save()

    i = Icon('people', width=1.8)
    i.circle(8, 9, 3)
    i.circle(16, 9, 3)
    i.arc(8, 19, 5, 180, 360)
    i.arc(16, 19, 5, 180, 360)
    i.save()


# ---- 仮の背景 ----

BACKGROUNDS = [
    ('lounge', '世界観/舞台/川崎/高層テラス/カワサキの窓辺テラスラウンジ.png', 0.30, 1.0, 1.0),
    ('garage_day', '世界観/舞台/テクノロジー工房/草薙モータース.png', 0.52, 1.05, 1.0),
    ('garage_night', '世界観/舞台/テクノロジー工房/草薙モータース.png', 0.45, 0.36, 0.6),
]


def backgrounds():
    """縦長（1080×1920）に切り抜き、ぼかす。fx は横の位置（0〜1）"""
    W, H = 1080, 1920
    for name, rel, fx, bright, sat in BACKGROUNDS:
        src = os.path.join(WORLD, rel)
        if not os.path.exists(src):
            print(f'背景の元の絵がない：{src}', file=sys.stderr)
            continue
        im = Image.open(src).convert('RGB')
        cw = im.height * W / H
        x0 = min(max(fx * im.width - cw / 2, 0), im.width - cw)
        im = im.crop((int(x0), 0, int(x0 + cw), im.height)).resize((W, H), Image.LANCZOS)
        im = im.filter(ImageFilter.GaussianBlur(14))
        im = ImageEnhance.Brightness(im).enhance(bright)
        im = ImageEnhance.Color(im).enhance(sat)
        if name == 'garage_night':   # 夜：青みを足す
            r, g, b = im.split()
            im = Image.merge('RGB', (r.point(lambda v: v * 0.8), g.point(lambda v: v * 0.95), b.point(lambda v: min(255, v * 1.15 + 6))))
        os.makedirs(os.path.join(OUT, 'Backgrounds'), exist_ok=True)
        im.save(os.path.join(OUT, 'Backgrounds', f'{name}.jpg'), quality=85)

    # 無地：中央の上が明るい、紺の放射状
    img = Image.new('RGB', (W // 4, H // 4))
    px = img.load()
    top, bottom = (42, 90, 120), (11, 26, 42)
    for y in range(img.height):
        for x in range(img.width):
            t = min(1.0, math.hypot((x - img.width / 2) / img.width, (y - img.height * 0.3) / img.height) * 1.6)
            px[x, y] = tuple(int(a + (b - a) * t) for a, b in zip(top, bottom))
    img.resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(6)).save(
        os.path.join(OUT, 'Backgrounds', 'plain.jpg'), quality=90)


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    circle()
    circle_outline()
    ring()
    ring(name='ring_dotted.png', stroke=2.0, dash=(2.5, 9))
    hexagon()
    hexagon_prism()
    glow()
    hex_glow()
    vertical_gradient()
    corner_arc()
    icons()
    backgrounds()
    print('書き出した：', OUT)
