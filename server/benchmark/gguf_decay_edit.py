"""Bounded, gradient-free edit of six GatedDeltaNet decay biases in Qwen35MoE.

The quantized matrices stay byte-identical. These GGUF tensors are already F32.
This is a hypothesis about stale recurrent state, not a localized loop circuit.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct

BASE_SHA256 = '3b46d1066bc91cc2d613e3bc22ce691dd77e6f0d33c9060690d24ce6de494375'
LAYERS = (12, 13, 14, 16, 17, 18)


def verify_patches(base, candidate, patches):
    """Verify both hashes and every byte, including unchanged bytes within targets."""
    ranges = sorted((offset, bytes(old), bytes(new)) for offset, old, new in patches)
    end = 0
    for offset, old, new in ranges:
        if offset < end or len(old) != len(new) or not old or old == new:
            raise ValueError('Invalid or overlapping patch')
        end = offset + len(old)
    if not ranges or end > base.stat().st_size:
        raise ValueError('Patch outside base')
    hashes = [hashlib.sha256(), hashlib.sha256()]
    changed = 0
    with base.open('rb') as a, candidate.open('rb') as b:
        start = 0
        while original := a.read(8 * 1024 * 1024):
            actual = b.read(len(original))
            expected = bytearray(original)
            for offset, old, new in ranges:
                lo, hi = max(start, offset), min(start + len(original), offset + len(old))
                if lo >= hi:
                    continue
                part = slice(lo - offset, hi - offset)
                if original[lo-start:hi-start] != old[part]:
                    raise ValueError('Base patch bytes changed')
                expected[lo-start:hi-start] = new[part]
                changed += sum(x != y for x, y in zip(old[part], new[part]))
            if actual != expected:
                raise ValueError('Candidate differs from exact planned patches')
            hashes[0].update(original)
            hashes[1].update(actual)
            start += len(original)
        if b.read(1) or not changed:
            raise ValueError('Invalid candidate size or empty edit')
    return dict(base_sha256=hashes[0].hexdigest(), candidate_sha256=hashes[1].hexdigest(),
                changed_bytes=changed, other_bytes_identical=True)


def shifted(values, amount):
    if amount not in (0.1, 0.25):
        raise ValueError('Registered exploration is +0.1 or +0.25 only')
    if len(values) != 32 or not all(math.isfinite(v) for v in values):
        raise ValueError('Expected 32 finite F32 biases')
    saved = struct.unpack('<32f', struct.pack('<32f', *(v + amount for v in values)))
    if any(not math.isfinite(v) or abs((v - old) - amount) > 1e-5
           for old, v in zip(values, saved)):
        raise ValueError('Invalid saved edit')
    return saved


def main():
    import gguf
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('base', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--shift', type=float, required=True)
    a = p.parse_args()
    if a.output.exists() or a.output.with_suffix('.json').exists():
        p.error('Candidate and manifest must be new')
    r = gguf.GGUFReader(str(a.base))
    for key, expected in [('general.architecture', 'qwen35moe'), ('qwen35moe.block_count', 40),
                          ('qwen35moe.embedding_length', 2048), ('qwen35moe.ssm.time_step_rank', 32)]:
        if r.fields[key].contents() != expected:
            raise ValueError('Unexpected architecture: ' + key)
    tensors = {t.name: t for t in r.tensors}
    patches, records = [], []
    for layer in LAYERS:
        t = tensors[f'blk.{layer}.ssm_dt.bias']
        decay = tensors[f'blk.{layer}.ssm_a']
        if t.tensor_type != gguf.GGMLQuantizationType.F32 or list(t.shape) != [32]:
            raise ValueError('Expected F32 bias')
        av = decay.data.reshape(-1).tolist()
        if len(av) != 32 or not all(math.isfinite(v) and v < 0 for v in av):
            raise ValueError('Expected negative decay A')
        old = t.data.reshape(-1).tolist()
        new = shifted(old, a.shift)
        before, after = struct.pack('<32f', *old), struct.pack('<32f', *new)
        patches.append((int(t.data_offset), before, after))
        records.append(dict(tensor=t.name, offset=int(t.data_offset), old=old, new=new,
                            delta_norm=math.sqrt(sum((v-u)**2 for u,v in zip(old,new)))))
    # Verify the original before copying; wrong revisions must never produce a candidate.
    h = hashlib.sha256()
    with a.base.open('rb') as f:
        for block in iter(lambda: f.read(8*1024*1024), b''):
            h.update(block)
    if h.hexdigest() != BASE_SHA256:
        raise ValueError('Unregistered base revision')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.base.open('rb') as src, a.output.open('xb') as dst:
        shutil.copyfileobj(src, dst, 8*1024*1024)
    with a.output.open('r+b') as dst:
        for offset, old, new in patches:
            dst.seek(offset)
            dst.write(new)
    verification = verify_patches(a.base, a.output, patches)
    if verification['base_sha256'] != BASE_SHA256:
        raise ValueError('Base changed during edit')
    report = dict(schema='ciel-gguf-decay-edit-v1', base=str(a.base), candidate=str(a.output),
                  shift=a.shift, layers=LAYERS, affected_weights=192, tensors=records,
                  hypothesis='Increase softplus(alpha + dt_bias); negative A strengthens decay. '
                             'May reduce stale state, but may damage useful memory. No causal localization.',
                  **verification)
    a.output.with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k != 'tensors'}), flush=True)


if __name__ == '__main__':
    main()
