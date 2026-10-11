"""Explicit candidate setup. No latest-file auto-adoption."""
import sys
import copy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import *

def part(name, filename, scale, offset, z, reason):
    path = GEN/'parts'/filename
    im = rgba(path)
    return dict(name=name,source=path.relative_to(ROOT).as_posix(),sha256=sha(path),source_size=list(im.size),matrix=[scale,0,offset[0],0,scale,offset[1]],anchor_canvas=[1095,370],z=z,opacity=1,blend='normal',status='candidate, awaiting composite inspection',corrections=[],placement_reason=reason)

def candidate1():
    c = read_json(GEN/'placement-stage1.json')
    c['stage'] = '2: candidate 01, not adopted'
    for p in c['layers']:
        if p['name'] in ['Hair_Front','Hair_Side_L','Hair_Side_R']:
            p['enabled']=False
        if p['name']=='Hair_Ahoge':
            correction(p,1,dy=55)
        if p['name']=='Choker_Back':
            correction(p,1,dy=12)
    c['layers'].append(part('Hair_Front_New','Hair_Front-01.png',.82,[578,177],180,'分け目(630,235)を(1095,370)付近、中央毛先を目の間へ。等方倍率。'))
    c['layers'].append(dict(name='Neck_Shadow_Chin',type='shadow',clip_to='Neck',color=[178,163,189],opacity=.48,full_until_y=1390,fade_end_y=1550,z=35,blend='normal',status='candidate',ownership='顎の落ち影。首土台にクリップ。顔・首輪とは別層。'))
    write_json(GEN/'placement-candidate01.json',c)
    layers,comp = render(c,GEN/'candidate01')
    on_bg(comp).crop(HEAD).save(GEN/'references/current-head-01.png')
    print('Candidate 01 rendered')

INNER = [[540,88],[[376,144],[249,319],[238,503]],[[220,730],[266,990],[448,1080]],[[425,1040],[415,1010],[405,983]],[[466,1047],[578,1079],[647,1053]],[[602,1032],[561,988],[536,941]],[[582,960],[644,970],[689,964]],[[616,942],[561,868],[536,777]],[[595,832],[690,844],[748,822]],[[591,849],[418,439],[499,180]],[[510,141],[527,108],[540,88]]]
LONG = [[384,88],[[434,116],[494,140],[512,168]],[[528,191],[528,232],[544,281]],[[612,508],[744,809],[651,1005]],[[650,1115],[681,1205],[745,1243]],[[700,1221],[661,1177],[638,1131]],[[655,1268],[699,1354],[789,1397]],[[653,1370],[515,1283],[495,1113]],[[497,1198],[510,1241],[535,1274]],[[435,1218],[433,1053],[445,894]],[[408,963],[355,1007],[301,1017]],[[388,962],[432,732],[438,625]],[[383,589],[354,518],[347,419]],[[333,310],[362,185],[384,88]]]

def candidate2():
    c=read_json(GEN/'placement-candidate01.json')
    c['stage']='2: candidate 02 with cheek and front long hair; not adopted'
    for p in c['layers']:
        if p['name'].startswith('Brow_'):
            p['z']=200 if p['name']=='Brow_R' else 201
        if p['name']=='Hair_Front_New':
            p['remove_detached_alpha']=True
        if p['name']=='Neck':
            # Widen around neck center: cover inherited torso's white standing collar.
            a,b,x,d,e,y=p['matrix']
            p['matrix']=[a*1.18,b,x*1.18+1117*(1-1.18),d,e,y]
            p['nonuniform_reason']='首幅を18%だけ増やし、顎下と首輪内側の接続を確保。v8の白い立ち襟が首輪内へ露出する量を減らす。'
    for side in ['R','L']:
        inner=part('Hair_Side_'+side+'_Inner','Hair_Side_R_Inner-01.png',.50,[515,773],171,'頬への2つの主要毛先を原画の高さへ。')
        inner['source_bezier']=INNER
        inner['mask_reason']='生成原本の輪郭外にある広い白いハローを手動ベジェ輪郭で除外。色閾値による一律消去はしない。'
        long=part('Hair_Side_'+side+'_LongFront','Hair_Side_R_LongFront-01.png',.52,[526,1030],170,'根元を頬髪の後ろへ入れ、主毛先を胸の宝石の横に置く。')
        long['source_bezier']=LONG
        long['mask_reason']=inner['mask_reason']
        if side=='L':
            for p in [inner,long]:
                a,b,x,d,e,y=p['matrix'];p['matrix']=[-a,-b,2210-x,d,e,y]
                p['mirrored_from']='character R original, reflected around canvas x1105; left shape reviewed in composite'
            correction(inner,1,dx=8,dy=-10,pivot=[1450,1100],angle=-2)
            correction(long,1,dx=-5,dy=-8,pivot=[1450,1300],angle=1.5)
        c['layers'] += [long,inner]
    write_json(GEN/'placement-candidate02.json',c)
    layers,comp=render(c,GEN/'candidate02')
    on_bg(comp).crop(HEAD).save(GEN/'references/current-head-02.png')
    print('Candidate 02 rendered')

def candidate3():
    c=read_json(GEN/'placement-candidate02.json')
    c['stage']='2: candidate 03, restored v8 original front, not adopted'
    for p in c['layers']:
        n=p['name']
        if n=='Hair_Front_New':
            src=ROOT/'assets/ciel/generated/v8/parts/Hair_Front.png'
            p.update(source=src.relative_to(ROOT).as_posix(),sha256=sha(src),matrix=[.82,0,582,0,.82,184],placement_reason='短くしたv2ではなくv8初版を別候補として復元。分け目と中央毛先で等方配置。')
        if n.endswith('_LongFront'):
            a,b,x,d,e,y=p['matrix'];pivot=760 if '_R_' in n else 1450
            p['matrix']=[a*1.45,b*1.45,x*1.45+pivot*(1-1.45),d,e,y]
            p['nonuniform_reason']='細すぎる手前髪の幅を試験的に45%拡大。輪郭の曲率を合成で比較する候補。'
        if n.endswith('_Inner'):
            correction(p,1,dy=-28)
    write_json(GEN/'placement-candidate03.json',c)
    layers,comp=render(c,GEN/'candidate03')
    sheet([rgba(GEN/'candidate02/compose.png'),comp],['新前髪01','v8初版を復元'],GEN/'candidate03/front-options.png',HEAD,.5)
    on_bg(comp).crop(HEAD).save(GEN/'references/current-head-03.png')
    print('Candidate 03 rendered')

def candidate4():
    c=read_json(GEN/'placement-candidate02.json')
    c['stage']='2: candidate 04 cohesive front hairstyle, not adopted'
    for p in c['layers']:
        if p['name']=='Hair_Front_New' or '_Inner' in p['name'] or '_LongFront' in p['name']:
            p['enabled']=False
    p=part('Hair_FrontAssembly','Hair_FrontAssembly-01.png',1.23,[315,223],180,'一続きの前髪・頬髪・胸の髪を原画の分け目、中央先端、胸の毛先で等方配置。採用前に合成し、粗い層分割を別途行う。')
    p['remove_detached_alpha']=True
    c['layers'].append(p)
    write_json(GEN/'placement-candidate04.json',c)
    layers,comp=render(c,GEN/'candidate04')
    on_bg(comp).crop(HEAD).save(GEN/'references/current-head-04.png')
    print('Candidate 04 rendered')

def candidate5():
    c=read_json(GEN/'placement-candidate04.json')
    c['stage']='2: candidate 05 final contacts/edges, awaiting inspection'
    c['layers']=[p for p in c['layers'] if p.get('enabled',True)]
    for p in c['layers']:
        if p['name']=='Hair_FrontAssembly':
            p['alpha_gain']=255/253
            p['logical_parts']=['Hair_Crown','Hair_Front','Hair_Side_R_Inner','Hair_Side_L_Inner','Hair_Side_R_LongFront','Hair_Side_L_LongFront']
            p['split_status']='段階2の形の確定用に一続きの原本を採用候補とする。動作層の分割・隠れた根元の描き足しは段階3。'
        if p['name'] in ['Ear_R','Ear_L']:
            p['z']=65 if p['name']=='Ear_R' else 66
        if p['name']=='Choker':
            pendant=copy.deepcopy(p)
            pendant.update(name='Choker_Pendant',source_rect=[0,750,1254,1254],z=59)
            correction(pendant,1,dy=-18,pivot=[1117,1600])
            pendant['mask_reason']='前帯の下端付近y750で丸飾りと接続タブを分離。18px上へ、帯の後ろへ入れ重ねて継ぐ。'
            p.update(name='Choker_Front',source_rect=[0,0,1254,749])
            p['remove_detached_alpha']=True
    c['layers'].append(pendant)
    c['layers'].append(dict(name='Choker_Inside',type='ellipse',box=[949,1359,1281,1492],color=[34,41,54],z=21,blend='normal',ownership='首輪内側の暗い空間。背面帯より手前・首より後ろ。v8胴側の白い立ち襟の露出を覆う。影ではなく首輪内面の補助マスク。',status='candidate'))
    c['layers'].append(dict(name='Face_Shadow_Hair',type='cast_shadow',owner='Hair_FrontAssembly',clip_to='Face_Skin',offset=[5,12],edge_blur=3,color=[171,159,187],opacity=.25,z=75,blend='normal',ownership='髪が額・頬へ落とす影。髪の内部陰影とは別。顔にクリップ、目鼻口より後ろ。',status='candidate'))
    write_json(GEN/'placement-candidate05.json',c)
    layers,comp=render(c,GEN/'candidate05',True)
    eyes=[]
    for scale in [1,1.05,1.10]:
        opt=copy.deepcopy(c)
        for p in opt['layers']:
            if p['name'].startswith('Eye_'):
                correction(p,scale/1.05,pivot=[930 if p['name']=='Eye_R' else 1282,1050])
        views=layers_for(opt)
        eyes.append(composite(views))
        write_json(GEN/('placement-eye-'+str(round(scale*100))+'.json'),opt)
    sheet(eyes,['目100%','目105%（候補）','目110%'],GEN/'candidate05/eye-options.png',HEAD,.5)
    sheet([comp,comp,comp],['白背景','中間灰','暗背景'],GEN/'candidate05/edges-head.png',HEAD,.5)
    # distinct backgrounds, same crop and zoom
    edge=Image.new('RGB',(1536,816))
    for j,col in enumerate([(250,250,252,255),(128,128,138,255),(18,22,34,255)]):
        tile=on_bg(comp,col).crop(HEAD).resize((512,512),Image.Resampling.LANCZOS)
        edge.paste(tile,(j*512,48))
        ImageDraw.Draw(edge).text((j*512+12,12),['白','中間灰','暗'][j],font=font(),fill='white')
    edge.crop((0,0,1536,560)).save(GEN/'candidate05/edges-head.png')
    on_bg(comp).crop(HEAD).save(GEN/'references/current-head-05.png')
    print('Candidate 05 rendered')

def candidate6():
    c=read_json(GEN/'placement-candidate05.json')
    c['stage']='2: candidate 06 individual eye balance and pendant clearance'
    for p in c['layers']:
        if p['name']=='Eye_R':
            correction(p,1.08/1.05,pivot=[930,1050])
            p['placement_reason']='右目は虹彩の縦幅が短いため基準から108%。中心を維持。'
        if p['name']=='Eye_L':
            correction(p,1/1.05,dx=-25,dy=3,pivot=[1282,1050])
            p['placement_reason']='左目は基準100%へ戻し、25px内側・3px下。左右の虹彩径と目の間隔を原画と比較。'
        if p['name']=='Choker_Pendant':
            correction(p,1,dy=-12,pivot=[1117,1600])
    write_json(GEN/'placement-candidate06.json',c)
    layers,comp=render(c,GEN/'candidate06')
    master=rgba(ROOT/'assets/ciel/master/ciel-upper-body-2x.png')
    sheet([master,rgba(GEN/'candidate05/compose.png'),comp],['原画','両目105%','右108%／左100%・位置補正'],GEN/'candidate06/eye-balance.png',HEAD,.5)
    print('Candidate 06 rendered')

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='6':candidate6()
    elif len(sys.argv)>1 and sys.argv[1]=='5':candidate5()
    elif len(sys.argv)>1 and sys.argv[1]=='4':candidate4()
    elif len(sys.argv)>1 and sys.argv[1]=='3':candidate3()
    elif len(sys.argv)>1 and sys.argv[1]=='2':candidate2()
    else:candidate1()
