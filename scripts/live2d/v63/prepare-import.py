"""Package the approved tail pixels as a two-layer PSD for native Cubism import."""
from pathlib import Path
import io
import json
import shutil
import struct
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'.local/tail-integration'
WORK = ROOT/'.local/tail-integration'


def u16(n): return struct.pack('>H', n)
def u32(n): return struct.pack('>I', n)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    src = ROOT/'assets/ciel/current/layers/Tail_Right.png'
    im = Image.open(src).convert('RGBA')
    w, h = im.size
    records, channels = [], []
    for name in ('Tail_Left', 'Tail_Right'):
        data = [b'\0\0'+im.getchannel(c).tobytes() for c in ('R', 'G', 'B', 'A')]
        record = struct.pack('>iiiiH', 0, 0, h, w, 4)
        record += b''.join(struct.pack('>hI', i, len(d)) for i, d in zip((0, 1, 2, -1), data))
        record += b'8BIMnorm'+bytes([255, 0, 0, 0])
        text = bytes([len(name)])+name.encode('ascii')
        text += b'\0'*((-len(text)) % 4)
        extra = u32(0)+u32(0)+text
        records.append(record+u32(len(extra))+extra)
        channels.extend(data)
    info = struct.pack('>h', -2)+b''.join(records)+b''.join(channels)
    info += b'\0'*(len(info) % 2)
    layers = u32(len(info))+info+u32(0)
    canvas = Image.new('RGBA', (2172, 2896))
    canvas.paste(im, (0, 0))
    header = b'8BPS'+u16(1)+b'\0'*6+u16(4)+u32(2896)+u32(2172)+u16(8)+u16(3)
    resolution = struct.pack('>IHHIHH', 72*65536, 1, 1, 72*65536, 1, 1)
    resources = b'8BIM'+u16(1005)+b'\0\0'+u32(len(resolution))+resolution
    psd = header+u32(0)+u32(len(resources))+resources+u32(len(layers))+layers+u16(0)
    psd += b''.join(canvas.getchannel(c).tobytes() for c in ('R', 'G', 'B', 'A'))
    (WORK/'tail-additions.psd').write_bytes(psd)
    check = Image.open(io.BytesIO(psd))
    assert check.size == canvas.size
    baseline = ROOT/'.local/tail-adoption/before/ciel.cmo3'
    assert baseline.exists(), 'Restore the pre-tail model locally before rebuilding the import'
    for name in ('before.cmo3', 'imported.cmo3'):
        if not (WORK/name).exists():shutil.copy2(baseline, WORK/name)
    (OUT/'layers.json').write_text(json.dumps({'canvas': [2172, 2896],
        'out': 'assets/ciel/psd/ciel-tail-additions-v63',
        'layers': [{'name': n, 'path': f'assets/ciel/current/layers/{n}.png',
                    'canvas': [w, h], 'offset': [0, 0]} for n in ('Tail_Left', 'Tail_Right')],
        'note': 'Same approved texture for both views; left geometry is reflected in the native rig.'},
        ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('TAIL_IMPORT_READY', len(psd), flush=True)


if __name__ == '__main__': main()
