"""Bind the pooled tear overlays to their respective blink parameters."""
from pathlib import Path
import sys,importlib.util
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import cmo3_tool as t
sp=importlib.util.spec_from_file_location('relaxed',HERE/'integrate-relaxed.py');lib=importlib.util.module_from_spec(sp);sp.loader.exec_module(lib)
doc=t.Cmo3(sys.argv[1]);e=lib.lib.Editor(doc)
for side in 'LR':
 if not lib.form_parameter(e,e.meshes[f'Tears_{side}_Teary'],f'ParamEye{side}Open'):
  e.opacity_binding(f'Tears_{side}_Teary',f'ParamEye{side}Open',True,key_values=(0,.5,1))
e.flush();doc.save(sys.argv[2]);print('TEARY_BLINK_BOUND')
