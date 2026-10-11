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

def main():
    items=[('v14 large',ROOT/'assets/ciel/generated/v14/selected/large-04.png')]
    items += [(p.stem,p) for p in sorted((GEN/'candidates').glob('*.png'))]
    results={}; annotated=[]; faces=[]; zooms=[]
    for name,path in items:
        im=Image.open(path).convert('RGB')
        result=corners(im)
        result['threshold_sensitivity']={str(t):corners(im,t)['height_difference_input_px'] for t in (8,12,16,20)}
        results[name]=result
        faces.append((name,im))
        zooms.append((name,im.crop(ROI)))
        view=im.crop(ROI).resize((700,500),Image.Resampling.NEAREST)
        draw=ImageDraw.Draw(view)
        points=[]
        for key,color in (('left_input_xy','#00a0ee'),('right_input_xy','#ee5090')):
            x,y=result[key]; x=(x-ROI[0])*4;y=(y-ROI[1])*4
            draw.line((0,y,700,y),fill=color,width=2)
            draw.ellipse((x-6,y-6,x+6,y+6),outline=color,width=2)
        annotated.append((f'{name}: dy={result["height_difference_input_px"]:.1f} input px',view))
    panel(faces,PROOF/'candidates.png',cols=4,side=400)
    panel(zooms,PROOF/'candidate-mouths.png',cols=2,side=525,height=375)
    panel(annotated,PROOF/'corner-measurements.png',cols=2,side=700,height=500)
    # Face axis from unchanged v14 nose and chin, measured without moving artwork.
    nose_alpha=np.asarray(Image.open(ROOT/'assets/ciel/layers/v14/Nose.png'))[:,:,3]
    y,x=np.where(nose_alpha>128)
    nose=(np.array([(x.min()+x.max())/2,(y.min()+y.max())/2])-np.array([318,236]))*1254/1536
    skin_alpha=np.asarray(Image.open(ROOT/'assets/ciel/layers/v14/Face_Skin.png'))[:,:,3]
    y,x=np.where(skin_alpha>128);bottom=y.max();xs=x[y>=bottom-1]
    chin=(np.array([(xs.min()+xs.max())/2,bottom])-np.array([318,236]))*1254/1536
    bb=results['large-01']['pigment_bbox_input']
    center=np.array([(bb[0]+bb[2]-1)/2,(bb[1]+bb[3]-1)/2])
    axis_x=nose[0]+(chin[0]-nose[0])*(center[1]-nose[1])/(chin[1]-nose[1])
    results['centering']={'nose_input_xy':nose.tolist(),'chin_input_xy':chin.tolist(),
        'mouth_bbox_center_input_xy':center.tolist(),'nose_chin_axis_x_at_mouth_center':float(axis_x),
        'horizontal_offset_from_axis_input_px':float(center[0]-axis_x),
        'horizontal_offset_from_axis_canvas_px':float((center[0]-axis_x)*1536/1254)}
    im=Image.open(GEN/'candidates/large-01.png').convert('RGB')
    draw=ImageDraw.Draw(im)
    draw.line((*nose,*chin),fill='#00a0ee',width=1)
    for point,color in ((nose,'#00a0ee'),(chin,'#00a0ee'),(center,'#ee5090')):
        x,y=point;draw.ellipse((x-3,y-3,x+3,y+3),outline=color,width=1)
    panel([('Nose - chin axis / mouth center',im.crop((350,550,930,1000)))],
          PROOF/'center-alignment.png',cols=1,side=696,height=540)
    write(GEN/'extraction/corner-measurements.json',results)
    print(results)

if __name__=='__main__': main()
