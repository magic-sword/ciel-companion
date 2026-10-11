"""v10: preserve approved pixels; assign ownership masks and generated underpaint.

All outputs are confined to the three v10 directories. No v9 file is modified.
Run with python -B scripts/live2d/v10/build.py.
"""
from pathlib import Path
import json, hashlib, shutil, warnings
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    from scipy import ndimage as ndi
    from scipy.spatial import ConvexHull

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT/'assets/ciel/layers/v9'
OUT = ROOT/'assets/ciel/layers/v10'
GEN = ROOT/'assets/ciel/generated/v10'
W,H = 2172,2896
SIZE = (W,H)
Y,X = np.mgrid[:H,:W]
records=[]
layers={}
def dump(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def read(name): return Image.open(SRC/(name+'.png')).convert('RGBA')
def blank(): return Image.new('RGBA',SIZE)
def cut(im,mask):
    a=np.array(im); a[:,:,3]=np.rint(a[:,:,3].astype(float)*np.asarray(mask)).astype('uint8')
    a[a[:,:,3]==0,:3]=0
    return Image.fromarray(a)
def maskpoly(points):
    m=Image.new('1',SIZE); ImageDraw.Draw(m).polygon(points,fill=1)
    return np.asarray(m)
def ellipse(box):
    m=Image.new('L',SIZE); ImageDraw.Draw(m).ellipse(box,fill=255)
    return np.asarray(m)>0
def fullcolor(rgb,mask):
    a=np.zeros((H,W,4),dtype='uint8'); a[:,:,:3]=rgb; a[:,:,3]=np.rint(np.asarray(mask)*255).astype('uint8')
    return Image.fromarray(a)
def comp(seq):
    result=blank()
    for im in seq: result.alpha_composite(im)
    return result
def register(name,im,z,desc,hidden_by,motion,visible=True,group=None,source='v9',clip=None):
    im.save(OUT/(name+'.png'))
    layers[name]=im
    records.append(dict(name=name,path=f'assets/ciel/layers/v10/{name}.png',z=z,visible=visible,
                        description=desc,hidden_by=hidden_by,motion=motion,group=group,source=source,clip=clip))
def reuse(name,z,desc,motion,hidden_by='上位の部位'):
    im=read(name)
    register(name,im,z,desc,hidden_by,motion)
    # Keep source bytes too, so unchanged assets have equal SHA256.
    shutil.copyfile(SRC/(name+'.png'),OUT/(name+'.png'))
def place_crop(im,box,target):
    crop=im.crop(box); crop=crop.crop(crop.getbbox())
    # Premultiplied alpha avoids dark/white fringes in resized generated art.
    crop=crop.convert('RGBa').resize((target[2]-target[0],target[3]-target[1]),Image.Resampling.LANCZOS).convert('RGBA')
    out=blank(); out.paste(crop,target[:2]); return out

def clean_round_iris(im,cx,cy,r,protected=None):
    """Matte the iris against its former white sclera; fill hidden circular top.

    The nearest blue is an edge-colour estimate, not an extra painted contour.
    Whitened edge pixels become transparent blue, preserving a white composite.
    """
    box=(cx-r-2,cy-r-2,cx+r+3,cy+r+3)
    a=np.array(im.crop(box)); rgb=a[:,:,:3].astype(float)
    good=(rgb[:,:,2]-rgb[:,:,0]>45)&(rgb[:,:,0]<140)&(a[:,:,3]>100)
    nearest=ndi.distance_transform_edt(~good,return_distances=False,return_indices=True)
    blue=rgb[nearest[0],nearest[1]]
    sy,sx=np.mgrid[:a.shape[0],:a.shape[1]]
    radial=np.sqrt((sx-(r+2))**2+(sy-(r+2))**2)
    circle=np.clip(r+.5-radial,0,1)
    missing=(a[:,:,3]<128)&(radial<r-3)&(sy<r+2-35)
    a[missing,:3]=blue[missing].astype('uint8'); a[missing,3]=255
    pale=(radial>r-6)&(rgb.min(2)>150)&(a[:,:,3]>0)
    bg=np.array([251.,251.,255.])
    vector=bg-blue
    opacity=np.clip(((bg-rgb)*vector).sum(2)/np.maximum((vector*vector).sum(2),1),0,1)
    # An edge-colour estimate avoids amplifying RGB compression noise at alpha~0.
    a[pale,:3]=np.uint8(np.rint(np.clip(blue[pale],0,255)))
    a[pale,3]=np.uint8(np.rint(a[pale,3]*opacity[pale]))
    # Preserve the original visible oval; circular completion affects only the
    # hidden top. A forced circle on the visible bottom would cut approved pixels.
    top=sy<r+2-60
    if protected is not None:
        top &= ~np.asarray(protected)[box[1]:box[3],box[0]:box[2]]
    a[top,3]=np.uint8(np.rint(a[top,3]*circle[top]))
    a[(a[:,:,3]<24)&(radial>r-3)&top,3]=0
    a[a[:,:,3]==0,:3]=0
    out=blank(); out.paste(Image.fromarray(a),box[:2]); return out

def smooth_upper_lashes():
    """Close 1-2px mask notches without adding another eyelash contour."""
    for side in ['R','L']:
        path=OUT/('Eye_'+side+'_LashUpper.png')
        im=Image.open(path).convert('RGBA'); box=im.getbbox()
        a=np.array(im.crop(box)); opaque=a[:,:,3]>128
        closed=ndi.binary_closing(opaque,iterations=2)
        fill=closed&~opaque
        if fill.any():
            valid=opaque&(a[:,:,0]>=a[:,:,1])
            near=ndi.distance_transform_edt(~valid,return_distances=False,return_indices=True)
            a[fill,:3]=a[near[0][fill],near[1][fill],:3]
            a[fill,3]=253
            im.paste(Image.fromarray(a),box[:2]); im.save(path)

def owned_parts(im,owners,order,z,descriptions,motion,underpaint=None,overlap=32):
    """Disjoint original pixels + opaque-only hidden overlap; no duplicate lines.

    owners is an integer ownership map. Extensions are only beneath later owners.
    The generated, line-free underpaint supplies newly exposed hidden texels.
    """
    a=np.asarray(im)
    smooth=np.asarray(im.convert('RGBa').filter(ImageFilter.GaussianBlur(8)).convert('RGBA'))
    cover=np.zeros((H,W),bool)
    output={}
    for i,name in reversed(list(enumerate(order))):
        own=(owners==i)&(a[:,:,3]>0)
        part=cut(im,own)
        if underpaint is not None:
            ext=ndi.distance_transform_edt(~own)<=overlap
            ext &= ~own & cover & (a[:,:,3]>=240)
            joined,component_count=ndi.label(((own&(a[:,:,3]>128))|ext),structure=np.ones((3,3)))
            attached=np.unique(joined[own&(a[:,:,3]>128)])
            attached=attached[attached>0]
            ext &= np.isin(joined,attached)
            fill=cut(underpaint,ext)
            fa=np.array(fill); fa[ext,3]=255
            # Match generated underpaint to the neighbouring approved lock,
            # sampling beyond its outline so no contour is duplicated beneath it.
            safe=own & (a[:,:,3]>253) & (a[:,:,:3].mean(2)>210)
            safe=ndi.binary_erosion(safe,iterations=5)
            if safe.any() and ext.any():
                near=ndi.distance_transform_edt(~safe,return_distances=False,return_indices=True)
                edge=smooth[near[0][ext],near[1][ext],:3].astype(float)
                fa[ext,:3]=np.uint8(np.clip(edge*.92+fa[ext,:3]*.08,0,255))
            part=comp([Image.fromarray(fa),part])
        output[name]=part
        cover |= own
    for i,name in enumerate(order):
        register(name,output[name],z+i,descriptions[i],', '.join(order[i+1:]) or '根元以外は露出',motion,
                 source='v9画素の担当分離＋生成下塗りの隠れ領域')
    return output

def build():
    OUT.mkdir(parents=True,exist_ok=True); (OUT/'proofs').mkdir(exist_ok=True)
    v9=json.loads((SRC/'placement.json').read_text(encoding='utf-8'))
    dump(GEN/'input-sha256.json',{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in SRC.glob('*') if p.is_file()})
    texture=Image.open(GEN/'parts/Hair_Underpaint_01.png').convert('RGBA')
    # Use clean interior, not the generated outside halo or the drawn silhouette.
    texture=texture.crop((220,200,850,1240)).resize(SIZE,Image.Resampling.LANCZOS)
    a=np.array(texture); a[:,:,3]=255; texture=Image.fromarray(a)

    # Round backing is lower than all original rear hair. Its top remains behind
    # the approved crown; the y365 horizontal cut is fully underpainted.
    original_back=read('Hair_Back'); back_a=np.asarray(original_back)
    cut_x=np.where(back_a[365,:,3]>128)[0]; left,right=int(cut_x.min()),int(cut_x.max())
    cx=(left+right)/2; rx=(right-left)/2
    rounded_top=305+60*((X-cx)/rx)**2
    dome=(X>=left)&(X<=right)&(Y>=rounded_top)&(Y<440)
    backing=np.array(texture)
    join_weight=np.clip((Y-325)/40,0,1)
    for channel in range(3):
        backing[:,:,channel]=np.uint8(np.asarray(texture)[:,:,channel]*(1-join_weight)+back_a[365,:,channel][None,:]*join_weight)
    back=comp([cut(Image.fromarray(backing),dome),original_back])
    register('Hair_Back',back,0,'既存後ろ髪を保持し、y365の切れ目の下に丸い頭部を補完。頭頂の外形は前髪担当。',
             '耳、顔、前髪、体','頭XY・後ろ髪の揺れ',source='v9＋生成下塗り')
    for args in [('Body',10,'胴・服・菱形をv9のまま保持','体・呼吸'),
                 ('Choker_Back',20,'首輪の後帯','首'),('Choker_Inside',21,'首輪内側の暗部','首'),
                 ('Neck',30,'首土台','首'),('Neck_Shadow_Chin',35,'顎下の灰紫の落ち影','首＋頭XY'),
                 ('Outer_R',40,'上着とファーをv9のまま保持','肩・体'),('Outer_L',50,'上着とファーをv9のまま保持','肩・体'),
                 ('Choker_Pendant',59,'接続タブと丸飾り','首輪＋飾り揺れ')]: reuse(*args)

    front=read('Choker_Front'); a=np.asarray(front)
    buckle=maskpoly([(1080,1431),(1089,1428),(1142,1428),(1151,1435),(1151,1513),(1144,1520),(1088,1520),(1080,1513)])
    # Metal is extracted once; underlying band is reconstructed from same-row band pixels.
    band=np.array(front)
    for y in range(1428,1520):
        xs=np.where(buckle[y])[0]
        if xs.size:
            band[y,xs,:3]=band[y,1076,:3]
            band[y,xs,3]=255
    register('Choker_Front',Image.fromarray(band),60,'前帯。金具の下まで帯を補完。','Choker_Buckle','首輪の曲げ')
    register('Choker_Buckle',cut(front,buckle),61,'矩形金具とシアンの留め具。帯から分離。','なし','首輪追従、金具の剛性維持')

    # Ear material ownership follows the visible fur boundary, with root fur on top.
    ear_polys={
        'R':[(645,194),(727,218),(748,268),(777,303),(812,346),(775,363),(820,389),(789,410),(823,419),(786,460),(747,497),(697,546),(654,567),(662,531),(616,563),(622,530),(634,502),(604,518),(546,512),(563,476),(534,483),(558,441),(574,414),(534,401),(550,375),(529,375),(558,345),(545,326),(565,313),(608,286),(584,262),(648,241),(651,235)],
        'L':[(1553,226),(1505,239),(1509,256),(1464,279),(1490,297),(1448,330),(1466,340),(1437,367),(1461,384),(1438,409),(1460,427),(1427,444),(1452,460),(1410,481),(1447,510),(1494,552),(1543,583),(1534,542),(1578,561),(1562,523),(1601,536),(1584,501),(1621,509),(1600,477),(1635,463),(1609,430),(1632,416),(1604,386),(1631,367),(1606,348),(1624,332),(1596,312),(1610,299),(1569,279),(1590,255),(1538,250)]}
    for side in ['R','L']:
        im=read('Ear_'+side); a=np.asarray(im)
        inner=maskpoly(ear_polys[side])
        base=(Y>585) if side=='R' else (Y>610)
        owners=np.zeros((H,W),np.int8); owners[inner]=1; owners[base]=2
        # A continuous ear body must exist beneath the independently moving inner fur.
        outer=np.array(im)
        clean=inner
        # Nearest sample from the lavender inner-ear surface, excluding fur.
        color=(221,224,248) if side=='R' else (218,222,247)
        outer[clean,:3]=color; outer[clean,3]=255
        # Maintain original edge pixels on outer side, hide clean interior under inner fur.
        outer[base,3]=0
        ext=ndi.distance_transform_edt(~((a[:,:,3]>0)&~base))<40
        ext &= base & (a[:,:,3]>254)
        outer[ext,:3]=np.asarray(texture)[ext,:3]; outer[ext,3]=255
        register('Ear_'+side+'_Outer',Image.fromarray(outer),65+(side=='L')*.1,'耳の外形と内毛の下の連続面。人間耳なし。','内毛・付け根毛・前髪','耳の傾き')
        register('Ear_'+side+'_Inner',cut(im,inner&~base),65.02+(side=='L')*.1,'内側の白い毛。下地と線を二重に持たせない。','付け根毛・前髪','耳親＋内毛の小変形')
        register('Ear_'+side+'_Base',cut(im,base),179+(side=='L')*.1,'既存耳下部の接合毛。耳親を基礎に頭側へ根元固定。','頭頂・前髪','耳と頭の接合')

    reuse('Face_Skin',70,'目鼻口のない連続した顔。弱い頬の陰はv9土台に保持。','頭XY')
    reuse('Face_Shadow_Hair',75,'前髪・横髪が落とす影。通常合成のv9そのまま。','顔＋髪の変位')
    reuse('Nose',80,'v9の小さな鼻','顔')

    features=Image.open(GEN/'parts/Features_01.png').convert('RGBA')
    face=read('Face_Skin')
    # Skin helpers are sampled from the original face, then feathered only at
    # their outside edges. In neutral they coincide with the same face pixels.
    for label,box in [('Upper',(1010,1205,1200,1250)),('Lower',(1010,1250,1200,1350))]:
        skin=(X>=box[0])&(X<box[2])&(Y>=box[1])&(Y<box[3])
        feather=Image.fromarray((skin*255).astype('uint8')).filter(ImageFilter.GaussianBlur(7))
        register('Mouth_Skin_'+label,cut(face,np.asarray(feather)/255),89,'口周りのv9肌。口の外側で変形し境界を覆う。','口線・口内','口周りの変形')
    mouth=read('Mouth')
    register('Mouth_Line_Upper',cut(mouth,Y<1250),92,'承認済み微笑みの上半分。','なし','閉じた微笑み',group='mouth_closed')
    register('Mouth_Line_Lower',cut(mouth,Y>=1250),93,'承認済み微笑みの下半分。上線と合成して元の一本の線。','なし','閉じた微笑み',group='mouth_closed')
    for state,box,target in [('Small',(165,770,430,925),(1064,1242,1152,1277)),('Large',(680,765,920,940),(1060,1239,1156,1303))]:
        im=place_crop(features,box,target); a=np.asarray(im); rgb=a[:,:,:3].astype(float)
        occupied=a[:,:,3]>0
        # Each generated feature is mechanically separated, no redraw of neutral mouth.
        teeth=(rgb[:,:,0]>175)&(rgb[:,:,1]>160)&(rgb[:,:,2]>155)&occupied&(Y<target[1]+(target[3]-target[1])*.50)
        tongue=(rgb[:,:,0]-rgb[:,:,1]>30)&(rgb[:,:,0]>175)&occupied&(Y>target[1]+(target[3]-target[1])*.46)
        teeth=ndi.binary_dilation(teeth,iterations=1)&occupied
        tongue=ndi.binary_dilation(tongue,iterations=1)&occupied&~teeth
        dist=ndi.distance_transform_edt(occupied)
        line=occupied&(dist<=1.6)
        inside=np.array(im); filled=teeth|tongue
        inside[filled|line,:3]=(121,70,84)
        register('Mouth_'+state+'_Inside',Image.fromarray(inside),90,'新規生成の口腔。舌と八重歯の下まで連続。','舌・歯・口線','口の開閉',False,'mouth_'+state.lower(),'生成Features_01')
        for part,m,z in [('Tongue',tongue&~line,90.1),('Teeth',teeth&~line,90.2),('Line_Upper',line&(Y<(target[1]+target[3])/2),92),('Line_Lower',line&(Y>=(target[1]+target[3])/2),93)]:
            register('Mouth_'+state+'_'+part,cut(im,m),z,'新規開口差分の'+{'Tongue':'舌','Teeth':'小さな八重歯','Line_Upper':'上線','Line_Lower':'下線'}[part],
                     '口の開口縁','口の開閉',False,'mouth_'+state.lower(),'生成Features_01',clip='Mouth_'+state+'_Inside' if part in ['Tongue','Teeth'] else None)

    for side,z,cx,cy,rad in [('R',100,924,1053,73),('L',110,1288,1043,73)]:
        eye=read('Eye_'+side); a=np.asarray(eye); rgb=a[:,:,:3].astype(float)
        occupied=a[:,:,3]>0
        # Original blue silhouette includes dark rim, pupil and white highlights.
        blue=(rgb[:,:,2]-rgb[:,:,0]>70)&(rgb[:,:,1]>50)&(a[:,:,3]>100)
        blue &= (((X-cx)/77)**2+((Y-cy)/80)**2)<1.08
        blue &= Y>=cy-70
        sy,sx=np.where(blue)
        points=np.column_stack([sx,sy]); hull=ConvexHull(points)
        iris_region=maskpoly([tuple(p) for p in points[hull.vertices]])
        iris_region=ndi.binary_dilation(iris_region,iterations=2)
        # Dark blue rim also belongs to the moving iris. The eyelash is mauve;
        # leaving blue rim fragments there produces stationary chips in gaze.
        nearby=ndi.distance_transform_edt(~iris_region)<9
        blue_rim=(rgb[:,:,2]-rgb[:,:,0]>12)&(rgb[:,:,1]-rgb[:,:,0]>1)&(rgb[:,:,0]<140)&(rgb[:,:,1]<180)
        iris_region |= nearby&blue_rim&(Y>=cy-71)&occupied
        # Keep faint antialias border, while limiting the owner to the original visible iris.
        iris_region=iris_region&occupied
        # Upper lashes and fold have an actual transparent gap; connected components
        # identify the fold without a hard horizontal cut through the curved eyelid.
        lab,num=ndi.label(a[:,:,3]>12)
        sizes=np.bincount(lab.ravel()); main=1+np.argmax(sizes[1:])
        mainmask=lab==main
        fold=(occupied&~ndi.binary_dilation(mainmask,iterations=3))&(Y<1005)
        # Interpolated upper/lower lash bounds hand traced on the original eye.
        if side=='R':
            upper_pts=[(740,1060),(770,1040),(800,999),(840,975),(880,958),(925,958),(965,967),(994,991),(1015,1010)]
        else:
            upper_pts=[(1170,1015),(1200,985),(1230,964),(1270,950),(1310,950),(1350,961),(1390,989),(1425,1030),(1465,1060)]
        upper_y=np.interp(X,[p[0] for p in upper_pts],[p[1] for p in upper_pts])
        dark=(rgb[:,:,0]<175)&(rgb[:,:,1]<150)&occupied
        upper=dark&(Y<cy+63)&~iris_region&~fold
        # Pale sclera below lash, original lower edge line if any.
        lower=dark&~upper&~iris_region&~fold
        sclera=occupied&~iris_region&~upper&~lower&~fold
        # Continuous white beneath iris, with no baked duplicate iris.
        scl=np.array(cut(eye,sclera)); scl[iris_region,:3]=(251,251,255); scl[iris_region,3]=255
        register('Eye_'+side+'_Sclera',Image.fromarray(scl),z,'白目。虹彩の下も白で連続させた開口。','虹彩・まぶた・まつげ','まばたき開口／虹彩クリップ元')
        # New circular upper iris is invisible behind the upper eyelid skin;
        # all visible approved iris pixels override it.
        box=(130,175,460,520) if side=='R' else (620,175,950,520)
        irisfull=place_crop(features,box,(cx-rad,cy-rad,cx+rad,cy+rad))
        irisfull=cut(irisfull,ellipse((cx-rad,cy-rad,cx+rad-1,cy+rad-1)))
        irisfull=cut(irisfull,Y<cy-35)
        # Pick the four discrete white reflection dots, not the broad cyan gradient.
        highlight=np.zeros((H,W),bool)
        circles=[(926,1013,13),(927,1034,5),(893,1102,7),(968,1098,6)] if side=='R' else [(1277,1005,12),(1281,1025,5),(1244,1090,6),(1319,1092,6)]
        for hx,hy,hr in circles: highlight |= ((X-hx)**2+(Y-hy)**2)<=hr**2
        highlight &= iris_region
        raw=np.array(cut(eye,iris_region))
        # Replace only the detached specular dots by nearby iris pixels.
        nearest=ndi.distance_transform_edt(highlight,return_distances=False,return_indices=True)
        raw[highlight,:3]=raw[nearest[0][highlight],nearest[1][highlight],:3]
        irisfull=comp([cut(irisfull,~iris_region),Image.fromarray(raw)])
        irisfull=clean_round_iris(irisfull,cx,cy,rad,iris_region)
        register('Eye_'+side+'_Iris',irisfull,z+.1,'瞳孔込みの丸い虹彩。見える部分はv9、隠れる上端のみ生成素材。白い点光は分離。','まぶた肌・まつげ','視線、白目へのクリッピング',clip='Eye_'+side+'_Sclera',source='v9＋生成Features_01')
        register('Eye_'+side+'_Highlight',cut(eye,highlight),z+.2,'v9の白い点光。青い面反射は虹彩の彩色として保持。','まぶた','虹彩と一緒に移動',clip='Eye_'+side+'_Sclera')
        # Cover new hidden iris outside the old opening, using exact face pixels.
        aperture=iris_region|sclera
        fullalpha=np.asarray(irisfull)[:,:,3]>0
        ap_labels,ap_count=ndi.label(aperture&(a[:,:,3]>100))
        ap_sizes=np.bincount(ap_labels.ravel()); ap_main=ap_labels==(1+np.argmax(ap_sizes[1:]))
        covers=(fullalpha|(ndi.distance_transform_edt(~ap_main)<24))&~aperture
        covers &= ndi.distance_transform_edt(np.asarray(face)[:,:,3]>250)>12
        lidface=face
        # Underlay must also preserve the original gap beneath crease.
        register('Eye_'+side+'_LidSkin_Upper',cut(lidface,covers&(Y<cy)),z+.3,'丸い虹彩の上端を隠すv9色の上まぶた肌。','上まつげ・二重','まばたき上まぶた')
        register('Eye_'+side+'_LidSkin_Lower',cut(lidface,covers&(Y>=cy)),z+.31,'虹彩下端の必要範囲を隠す下まぶた肌。','下まつげ','まばたき下まぶた')
        for part,mask,off in [('LashUpper',upper,.4),('LashLower',lower,.5),('Crease',fold,.6)]:
            register('Eye_'+side+'_'+part,cut(eye,mask),z+off,{'LashUpper':'上まつげと目尻','LashLower':'下まつげ・下縁の線','Crease':'二重線'}[part]+'をv9から分離。','髪','まばたき／表情')
        closedbox=(40,1100,480,1260) if side=='R' else (605,1100,1040,1260)
        closed=place_crop(features,closedbox,(cx-115,cy-7,cx+112,cy+49))
        register('Eye_'+side+'_Closed',closed,z+.7,'上下まつげが合流した新規閉じ目線。開眼層と排他表示。','髪','閉眼の終端形',False,'eyes_closed','生成Features_01')

    reuse('Hair_Ahoge',140,'v9アホ毛。根元は冠の後ろ。','アホ毛揺れ')
    hair=read('Hair_FrontAssembly'); a=np.asarray(hair)
    # Three front locks + two cheek locks + two long locks + the crown.
    # Curves are ownership boundaries, not newly painted contour lines.
    left_boundary=np.interp(Y,[350,420,550,700,850,1000,1150,1260],[1085,985,845,755,719,731,805,855])
    right_boundary=np.interp(Y,[350,420,550,700,850,1000,1150,1260],[1110,1220,1370,1445,1477,1470,1405,1355])
    center_left=np.interp(Y,[350,420,550,700,850,1000,1120],[1090,1020,961,932,940,1010,1180])
    center_right=np.interp(Y,[350,420,550,700,850,1000,1120],[1105,1170,1220,1245,1235,1190,1180])
    names=['Hair_Side_R_LongFront','Hair_Side_L_LongFront','Hair_Side_R_Inner','Hair_Side_L_Inner',
           'Hair_Front_1','Hair_Front_3','Hair_Front_2']
    owners=np.full((H,W),6,dtype=np.int8)
    owners[(X<center_left)]=4; owners[(X>center_right)]=5
    owners[(X<left_boundary)]=2; owners[(X>right_boundary)]=3
    owners[(Y>1005)&(X<center_left)]=2
    owners[(Y>1005)&(X>center_right)]=3
    owners[(Y>=1200)&(X<1100)]=0; owners[(Y>=1200)&(X>=1100)]=1
    owners[(Y<370)&(X<1095)]=2
    owners[(Y<370)&(X>=1095)]=3
    descriptions=['画面左・胸へ下る長い手前髪。根元を頬髪の下へ32px補完。',
                  '画面右・胸へ下る長い手前髪。根元を頬髪の下へ32px補完。',
                  '画面左・頬を包む内側の横髪。前髪の下へ32px補完。',
                  '画面右・頬を包む内側の横髪。前髪の下へ32px補完。',
                  '画面左の前髪束。中央束の下へ32px補完。頭頂の丸みも分担。',
                  '画面右の前髪束。中央束の下へ32px補完。頭頂の丸みも分担。',
                  '目の間へ下る中央束。承認済みの毛先を保持。頭頂を水平に切らず、分け目で左右束と接続。']
    owned_parts(hair,owners,names,180,descriptions,'頭→各束。根元固定、毛先を個別に揺らす',texture,32)
    # Geometry definitions are reviewable and reproducible.
    np.savez_compressed(GEN/'ownership-masks.npz',hair=owners)
    reuse('Brow_R',200,'v9眉。前髪より上。','眉表情')
    reuse('Brow_L',201,'v9眉。前髪より上。','眉表情')
    smooth_upper_lashes()
    records.sort(key=lambda r:r['z'])
    for r in records:
        if r['name']=='Neck_Shadow_Chin': r['clip']='Neck'
        if r['name']=='Face_Shadow_Hair': r['clip']='Face_Skin'
    dump(OUT/'psd-manifest.json',dict(canvas=[W,H],out='assets/ciel/psd/ciel-v10',layers=[{k:r[k] for k in ['name','path']} for r in records]))
    dump(OUT/'layer-state.json',dict(canvas=[W,H],order='bottom_to_top',layers=records,
        presets={'neutral':dict(eyes='open',mouth='closed'),'blink':dict(eyes='closed',mouth='closed'),
                 'talk_small':dict(eyes='open',mouth='small'),'talk_large':dict(eyes='open',mouth='large')}))
    return v9

if __name__=='__main__':
    build()
    print('Wrote',len(records),'full-canvas layers')
