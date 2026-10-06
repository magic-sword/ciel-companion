"""Read the approved eye reference in GIMP for the current motion builder."""
import os
from pathlib import Path
ROOT = Path(os.environ['CIEL_PROJECT_ROOT'])
exec((ROOT/'scripts/gimp/eye_material_core.py').read_text(encoding='utf-8'))
approved = ROOT/'docs/assets/ciel/production/ciel-eye-appearance-study-v1.png'
src = Gimp.file_load(Gimp.RunMode.NONINTERACTIVE, Gio.File.new_for_path(str(approved)))
sw, sh = src.get_width(), src.get_height()
assert (sw, sh) == (2172,724)
buf = bytes(src.get_layers()[0].get_buffer().get(Gegl.Rectangle.new(0,0,sw,sh),1.0,FMT,Gegl.AbyssPolicy.NONE))
def read(x,y):
    x=max(0,min(sw-2,x)); y=max(0,min(sh-2,y))
    ix,iy=int(x),int(y); fx,fy=x-ix,y-iy
    return [sum(buf[4*((iy+dy)*sw+ix+dx)+c]*wx*wy
                for dx,wx in ((0,1-fx),(1,fx)) for dy,wy in ((0,1-fy),(1,fy))) for c in range(3)]
