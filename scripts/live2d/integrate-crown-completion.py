"""Replace the common crown/back-hair sources and extend the crown mesh."""
from pathlib import Path
import importlib.util, sys
from PIL import Image
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import cmo3_tool as t, mesh_ops
spec = importlib.util.spec_from_file_location('expressions', HERE/'integrate-expressions.py')
lib = importlib.util.module_from_spec(spec); spec.loader.exec_module(lib)
doc = t.Cmo3(sys.argv[1]); editor = lib.Editor(doc)
for name in ('Hair_Crown', 'Hair_Back'):
    editor.replace_image(name, ROOT/'assets/ciel/generated/v47/layers'/f'{name}.png')
editor.flush()
box = Image.open(ROOT/'assets/ciel/generated/v47/layers/Hair_Crown.png').getbbox()
mesh_ops.remesh_rect(doc, 'Hair_Crown', (box[0]-4, box[1]-4, box[2]+4, box[3]+4), 32, 16)
doc.save(sys.argv[2])
print('CROWN_COMPLETION_INTEGRATED', box, 33*17)
