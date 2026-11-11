"""Experimental Q6_K EOS-row scale edit; requires gguf==0.19.0 and numpy.

Copies the base, edits eight fp16 block scales, verifies all other bytes.
This tests a stopping hypothesis, not the published small-model neuron edit.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(data)
    return h.hexdigest()


def main():
    import gguf
    import numpy as np
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('base', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--factor', type=float, default=1.05)
    a = p.parse_args()
    if not math.isfinite(a.factor) or not 1 < a.factor <= 1.1:
        p.error('Exploration restricted to 1 < factor <= 1.1')
    if a.output.exists() or a.output.with_suffix('.json').exists():
        p.error('Candidate and manifest must be new')
    r = gguf.GGUFReader(str(a.base))
    if r.fields['general.architecture'].contents() != 'qwen35moe':
        raise ValueError('Expected qwen35moe')
    eos = r.fields['tokenizer.ggml.eos_token_id'].contents()
    if r.fields['tokenizer.ggml.tokens'].contents(eos) != '<|im_end|>':
        raise ValueError('Unexpected EOS token')
    t = next(t for t in r.tensors if t.name == 'output.weight')
    if t.tensor_type != gguf.GGMLQuantizationType.Q6_K or list(t.shape) != [2048, 248320]:
        raise ValueError('Unexpected output shape or quantization')
    original = t.data[eos].copy()
    edited = original.copy().reshape(8, 210)
    scales = edited[:, 208:210].copy().view('<f2').reshape(8)
    scaled = (scales.astype(np.float32) * a.factor).astype('<f2')
    if not np.isfinite(scaled).all() or np.any(scaled == 0):
        raise ValueError('Invalid scales')
    edited[:, 208:210] = scaled.view(np.uint8).reshape(8, 2)
    edited = edited.reshape(-1)
    old = gguf.dequantize(original.reshape(1, -1), t.tensor_type)
    new = gguf.dequantize(edited.reshape(1, -1), t.tensor_type)
    expected = old.reshape(8, 256) * (scaled.astype(np.float32)/scales.astype(np.float32))[:, None]
    if not np.allclose(new.reshape(8, 256), expected, rtol=1e-6, atol=1e-7):
        raise ValueError('Dequantized scale check failed')
    rounding_error = float(np.linalg.norm(new-old*a.factor)/np.linalg.norm(old))
    if rounding_error > .01:
        raise ValueError('Scale rounding error exceeds 1%')
    start = int(t.data_offset) + eos * original.size
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.base.open('rb') as src, a.output.open('xb') as dst:
        shutil.copyfileobj(src, dst, 8 * 1024 * 1024)
    with a.output.open('r+b') as f:
        f.seek(start)
        f.write(edited.tobytes())
    allowed = {start + i for i in np.flatnonzero(original != edited)}
    changed = 0
    with a.base.open('rb') as src, a.output.open('rb') as dst:
        offset = 0
        while block := src.read(8 * 1024 * 1024):
            other = dst.read(len(block))
            if len(block) != len(other):
                raise ValueError('Size mismatch')
            if block != other:
                positions = np.flatnonzero(np.frombuffer(block, np.uint8) != np.frombuffer(other, np.uint8))
                if any(offset + int(i) not in allowed for i in positions):
                    raise ValueError('Unexpected byte change')
                changed += len(positions)
            offset += len(block)
        if dst.read(1) or changed != len(allowed) or not changed:
            raise ValueError('Incomplete verification')
    report = dict(base=str(a.base), candidate=str(a.output), base_sha256=digest(a.base),
                  candidate_sha256=digest(a.output), tensor=t.name, token=eos, factor=a.factor,
                  changed_bytes=changed, scale_values=8, affected_weights=2048,
                  delta_norm=float(np.linalg.norm(new-old)),
                  relative_delta_norm=float(np.linalg.norm(new-old)/np.linalg.norm(old)),
                  scale_rounding_relative_error=rounding_error,
                  original_scales=scales.tolist(), edited_scales=scaled.tolist(),
                  other_bytes_identical=True, gguf_version='0.19.0', numpy_version=np.__version__)
    a.output.with_suffix('.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
