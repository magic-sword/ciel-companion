"""Run an explicit local Python experiment script through the existing home SSH."""
import argparse
import base64
import json
import importlib.util
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('script', type=Path)
p.add_argument('--upload', type=Path, action='append', default=[])
p.add_argument('--save-json', type=Path, help='Save JSON-only remote output to a new local file')
a = p.parse_args()
s = importlib.util.spec_from_file_location('wsp_home', Path(__file__).with_name('weight-space-home.py'))
w = importlib.util.module_from_spec(s)
s.loader.exec_module(w)
payload = {f.name: base64.b64encode(f.read_bytes()).decode() for f in a.upload}
prefix = 'from pathlib import Path\nimport base64\nroot=Path.home()/"work/ciel-weight-space-quant"\nroot.mkdir(exist_ok=True)\n'
prefix += 'payload=' + repr(payload) + '\nfor name,data in payload.items():\n (root/name).write_bytes(base64.b64decode(data))\n'
if a.save_json:
    if a.save_json.exists():
        p.error('Output must be new')
    data = json.loads(w.remote(prefix + a.script.read_text(encoding='utf-8'), capture=True))
    a.save_json.parent.mkdir(parents=True, exist_ok=True)
    with a.save_json.open('x', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
else:
    w.remote(prefix + a.script.read_text(encoding='utf-8'))
