from pathlib import Path
import numpy as np
from PIL import Image
root=Path(__file__).resolve().parents[3]
a=np.array(Image.open(root/'assets/ciel/master/ciel-upper-body-2x.png')).astype(float)
f=np.array(Image.open(root/'assets/ciel/layers/v10/Face_Skin.png'))
for y in range(1240,1381,10):
    old=np.where(f[y,:,3]>128)[0][[0,-1]]
    result=[]
    for x in old:
        lo,hi=int(x)+18-30,int(x)+18+30
        rgb=a[y,lo:hi,:3]
        score=(rgb[:,0]-rgb[:,1])*(255-rgb.mean(1))
        xx=lo+np.argmax(score)
        result.append((int(xx),a[y,xx,:3].astype(int).tolist()))
    print(y,old.tolist(),result)
