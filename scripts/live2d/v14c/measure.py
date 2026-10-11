"""Measure generated pixels; never mirror, warp, rotate or relocate a mouth."""
import numpy as np
from PIL import Image, ImageDraw
from common import GEN, ROOT, PROOF, ROI, FONT, panel, write, ndi

def corners(im, threshold=12):
    a=np.asarray(im.convert('RGB')).astype(np.int16)
    x0,y0,x1,y1=ROI
    mask=np.zeros(a.shape[:2],bool)
    mask[y0:y1,x0:x1]=(a[y0:y1,x0:x1,0]-a[y0:y1,x0:x1,1]>threshold)&(a[y0:y1,x0:x1,1]<224)
    labels,n=ndi.label(mask)
    areas=np.bincount(labels.ravel()); areas[0]=0
    mask=labels==areas.argmax()
    yy,xx=np.where(mask)
    xmin,xmax=int(xx.min()),int(xx.max())
    result=[]
    # Median top contour within the outermost three colored columns.
    # This measures where upper/lower lips meet, not the centroid of a side wall.
    for columns in (range(xmin,xmin+3),range(xmax-2,xmax+1)):
        ys=[int(np.flatnonzero(mask[:,x])[0]) for x in columns]
        result.append([float(np.median(list(columns))),float(np.median(ys))])
    left,right=result
    delta=abs(left[1]-right[1])
    return {'left_input_xy':left,'right_input_xy':right,'height_difference_input_px':delta,
            'left_canvas_xy':[318+left[0]*1536/1254,236+left[1]*1536/1254],
            'right_canvas_xy':[318+right[0]*1536/1254,236+right[1]*1536/1254],
            'height_difference_canvas_px':delta*1536/1254,
            'mouth_center_input_x':(left[0]+right[0])/2,
            'pigment_bbox_input':[xmin,int(yy.min()),xmax+1,int(yy.max())+1]}
