"""Replace the seven approved skin images without changing geometry or bindings."""
from pathlib import Path
import importlib.util,json,sys
from PIL import Image
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));import cmo3_tool as t
sp=importlib.util.spec_from_file_location('integration',HERE/'integrate-expressions.py')
lib=importlib.util.module_from_spec(sp);sp.loader.exec_module(lib)
doc=t.Cmo3(sys.argv[1]);editor=lib.Editor(doc)
info=json.loads((ROOT/'assets/ciel/generated/v46/generation-provenance.json').read_text(encoding='utf-8'))
for entry in info['layers']:
    name=entry['name'];source=ROOT/'assets/ciel/current/layers'/(name+'.png')
    replacement=ROOT/'assets/ciel/generated/v46/layers'/(name+'.png')
    a=np.asarray(Image.open(source).convert('RGBA'));b=np.asarray(Image.open(replacement).convert('RGBA'))
    assert a.shape==b.shape and np.array_equal(a[:,:,3],b[:,:,3]),name
    editor.replace_image(name,replacement)
editor.flush();doc.save(sys.argv[2]);print('SKIN_IMAGES_INTEGRATED',len(info['layers']))
