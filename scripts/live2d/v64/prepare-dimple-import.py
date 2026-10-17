"""くぼみの影（Codex の A 案）を、Cubism に取り込むための 2 層の PSD にする（v64）。

層：Cheek_Dimple_L（画面の右）・Cheek_Dimple_R（画面の左）。どちらもキャンバスと同じ 2172×2896、元の位置のまま。
出力：.local/cheek-integration/cheek-dimple-additions.psd。Cubism で、段階 1 のモデル（cheek.cmo3）に
「PSD を追加で読み込む」で取り込み、imported.cmo3 として保存してから、integrate-dimple.py を使う。
"""
from pathlib import Path
import io
import struct

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
WORK = ROOT / '.local/cheek-integration'
LAYERS = {'Cheek_Dimple_L': 'Cheek_Dimple_L_A.png', 'Cheek_Dimple_R': 'Cheek_Dimple_R_A.png'}


def u16(n): return struct.pack('>H', n)
def u32(n): return struct.pack('>I', n)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    records, channels = [], []
    canvas = Image.new('RGBA', (2172, 2896))
    for name, file in LAYERS.items():
        im = Image.open(ROOT / 'assets/ciel/generated/v64' / file).convert('RGBA')
        assert im.size == canvas.size, (file, im.size)
        canvas.alpha_composite(im)
        w, h = im.size
        data = [b'\0\0' + im.getchannel(c).tobytes() for c in ('R', 'G', 'B', 'A')]
        record = struct.pack('>iiiiH', 0, 0, h, w, 4)
        record += b''.join(struct.pack('>hI', i, len(d)) for i, d in zip((0, 1, 2, -1), data))
        record += b'8BIMnorm' + bytes([255, 0, 0, 0])
        text = bytes([len(name)]) + name.encode('ascii')
        text += b'\0' * ((-len(text)) % 4)
        extra = u32(0) + u32(0) + text
        records.append(record + u32(len(extra)) + extra)
        channels.extend(data)
    info = struct.pack('>h', -len(LAYERS)) + b''.join(records) + b''.join(channels)
    info += b'\0' * (len(info) % 2)
    layers = u32(len(info)) + info + u32(0)
    header = b'8BPS' + u16(1) + b'\0' * 6 + u16(4) + u32(2896) + u32(2172) + u16(8) + u16(3)
    resolution = struct.pack('>IHHIHH', 72 * 65536, 1, 1, 72 * 65536, 1, 1)
    resources = b'8BIM' + u16(1005) + b'\0\0' + u32(len(resolution)) + resolution
    psd = header + u32(0) + u32(len(resources)) + resources + u32(len(layers)) + layers + u16(0)
    psd += b''.join(canvas.getchannel(c).tobytes() for c in ('R', 'G', 'B', 'A'))
    out = WORK / 'cheek-dimple-additions.psd'
    out.write_bytes(psd)
    assert Image.open(io.BytesIO(psd)).size == canvas.size
    print('DIMPLE_IMPORT_READY', out, len(psd))


if __name__ == '__main__':
    main()
