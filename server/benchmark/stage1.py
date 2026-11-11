"""Fixed independent construction fixtures, with genuinely different layouts."""
import copy

KINDS = ('clear','level','floor','wall','backfill','already_done','shortage','protected','hazard','no_stance','stop_continue','changed')


def coordinates(r):
    return [[x,y,z] for y in range(r['y1'],r['y2']+1) for x in range(r['x1'],r['x2']+1) for z in range(r['z1'],r['z2']+1)]


def fixture(kind, seed=11):
    if kind not in KINDS or seed not in (11,29,47,65):
        raise ValueError('Unknown stage1 fixture')
    holdout=seed!=11;fresh=seed in(47,65);third=seed==65
    r=dict(x1=-10 if third else -15 if fresh else -12 if holdout else 4,x2=-8 if third else -12 if fresh else -10 if holdout else 6,
           y1=64,y2=64,z1=12 if third else -7 if fresh else 4 if holdout else 0,z2=14 if third else -5 if fresh else 6 if holdout else 2)
    initial,preserve,expected=[],[],[]
    block='oak_planks';operation='floor';reason=None;inventory={};extras={}
    if kind in ('clear','level','protected'):
        operation='clear';r['y2']=65;r['z2']=r['z1']+1
        initial=[[*p,'dirt' if kind!='level' or i%3 else 'stone'] for i,p in enumerate(coordinates(r))]
        expected=[[*p,'air'] for p in coordinates(r)]
    if kind in ('clear','level','protected'):
        preserve=[[x,63,z,'grass_block'] for x in range(r['x1'],r['x2']+1) for z in range(r['z1'],r['z2']+1)]
        inventory={'iron_shovel':1,'iron_pickaxe':1}
        if kind=='clear':
            initial[1][3]='air'
        if kind=='protected':
            if holdout:
                reason='protected_overlap';extras['preserve_regions']=[{**r,'y2':64}]
            else:
                initial[-1][3]='oak_planks';reason='protected_block'
            expected=copy.deepcopy(initial)
    if kind=='floor':
        r['x2']=r['x1']+(2 if third else 4 if fresh else 3 if holdout else 7);r['z2']=r['z1']+(3 if third else 2 if fresh else 3 if holdout else 7)
        if holdout:r['y1']=r['y2']=65;block='glass'
        preserve=[[*p, 'grass_block'] for p in coordinates({**r,'y1':r['y1']-1,'y2':r['y1']-1})]
        side=r['z2']-r['z1']+1
        initial=[[*p,block] for p in coordinates(r)[side-2:side]]
        extras['pointing']={'points':[[r['x1'],r['y1']-1,r['z1']],[r['x2'],r['y1']-1,r['z2']]],'expected_face':[0,1,0]}
    if kind=='wall':
        operation='wall';block='stone' if holdout else 'cobblestone';r['y2']=66 if third else 67 if holdout else 66
        if holdout:r['x2']=r['x1'];r['z2']=r['z1']+(3 if third else 2 if fresh else 1)
        else:r['z2']=r['z1']
        initial=[[*coordinates(r)[0],block]]
    if kind=='backfill':
        operation='backfill';block='dirt';r['y1']=61;r['y2']=63;r['z2']=r['z1']+1
        initial=[[*p,'air'] for p in coordinates(r)]
        initial[0][3]='stone';initial[4][3]='dirt'
        expected=[[*p, 'stone' if i==0 else 'dirt'] for i,p in enumerate(coordinates(r))]
    if kind=='already_done':
        block='stone';initial=[[*p,block] for p in coordinates(r)]
    if kind=='shortage':block='glass';reason='missing_materials'
    if kind=='hazard':
        reason='hazard_near_region';x,y,z=r['x2']+2,64,r['z1']
        if holdout:
            initial += [[x,y,z,'water']]+[[x+dx,y+dy,z+dz,'glass'] for dx,dy,dz in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1))]
        else:initial.append([x,y,z,'sand'])
    if kind=='no_stance':
        r['y1']=r['y2']=73 if third else 72 if fresh else 71 if holdout else 70;reason='unsafe_stance'
    if kind in ('stop_continue','changed'):
        r['x2']=r['x1']+(2 if third else 4 if fresh else 3 if holdout else 7);r['z2']=r['z1']+(3 if third else 2 if fresh else 3 if holdout else 7)
    if operation not in ('clear',):
        if not expected:expected=[[*p,block] for p in coordinates(r)]
        occupied={tuple(p[:3]):p[3] for p in initial}
        inventory={block:sum(occupied.get(tuple(p[:3]))!=p[3] for p in expected)}
        if kind=='already_done':inventory={}
        if kind=='shortage':inventory[block]-=1
    if reason and operation!='clear':
        placed={tuple(p[:3]):p[3] for p in initial}
        expected=[[*p,placed.get(tuple(p),'grass_block' if p[1]==63 else 'stone' if p[1]<63 else 'air')] for p in coordinates(r)]
    outside=[r['x1']-1,64,r['z1']-1,'chest']
    preserve.append(outside)
    spec={'operation':operation,'region':r,'on_protected':'stop_before_edit'}
    if operation=='clear':spec['clear_blocks']=['dirt','stone'] if kind=='level' else ['dirt']
    else:spec['block']=block
    if kind=='level':spec['preserve_regions']=[{**r,'y1':63,'y2':63}]
    if extras.get('preserve_regions'):spec['preserve_regions']=extras['preserve_regions']
    axes=f"X={r['x1']}〜{r['x2']}、Y={r['y1']}〜{r['y2']}、Z={r['z1']}〜{r['z2']}"
    material={'oak_planks':'オークの板材','glass':'ガラス','cobblestone':'丸石','dirt':'土','stone':'石'}[block]
    prompt=f'{axes}に{material}で床を敷いてください。'
    if operation=='clear':prompt=f'{axes}の'+('土と石' if kind=='level' else '土')+'を全部取り除いてください。'
    if kind=='level':prompt+='Y=63の地面は残してください。'
    if kind=='wall':prompt=f'{axes}に{material}で壁を建ててください。'
    if kind=='backfill':prompt=f'{axes}の穴を土で埋め戻してください。既にある石と土は壊さず残してください。'
    if kind=='floor':prompt=f'今選んだ地面の2点の上に{material}で床を敷いてください。'
    if kind=='protected':
        prompt+='建物や保護対象が混じっていたら何も壊さず中止してください。'
        if holdout:prompt+=f"X={r['x1']}〜{r['x2']}、Y=64、Z={r['z1']}〜{r['z2']}は保護してください。"
    if kind=='changed':extras['external']=[r['x1'],64,r['z1'],'chest']
    task={'id':'s1_'+kind,'stage1':kind,'policy':'spatial-v1','prompt':prompt,'inventory':inventory,'forest':'none',
        'milestones':list(inventory),'region_spec':spec,'body_call':{'name':'minecraft_prepare_region','arguments':{}},
        'spatial':{'skill':'edit_region','initial':initial,'expected':expected,'preserve':preserve,'audit':True,
                   **({'expected_reason':reason} if reason else {})},
        'budget':{'seconds':120 if kind in ('floor','stop_continue','changed') else 90}}
    task['baseline_call']={'name':'minecraft_clear_region'if operation=='clear'else 'minecraft_build_region',
        'arguments':{**r,**({'block':block}if operation!='clear'else {})}}
    if 'pointing'in extras:task['pointing']=extras['pointing']
    if 'external'in extras:task['external']=extras['external']
    return task


def migrate_task(task):
    """Fixture migration only. The old call is retained solely for baseline tests."""
    t=copy.deepcopy(task)
    call=t.get('body_call',{})
    name,args=call.get('name'),call.get('arguments',{})
    if name not in ('minecraft_clear_region','minecraft_build_region') and not (name=='minecraft_pointed_action'and args.get('action')in('clear','floor')):
        return t
    t['baseline_call']=copy.deepcopy(call)
    if name=='minecraft_pointed_action':
        operation=args['action'];region=None
        if operation=='floor'and t.get('pointing'):t['pointing']['expected_face']=[0,1,0]
    else:
        region={k:args[k]for k in ('x1','x2','y1','y2','z1','z2')}
        operation='clear'if name=='minecraft_clear_region'else 'floor'if args['y1']==args['y2']else 'wall'
    t['region_spec']={'operation':operation,'on_protected':'stop_before_edit',**({'region':region}if region else {}),
                      **({'block':args['block']}if 'block'in args else {'clear_blocks':['dirt']}if operation=='clear'else {})}
    t['spatial']['skill']='edit_region'
    if operation=='clear':
        t['prompt']+='取り除く材質は土ブロックだけです。'
    t['body_call']={'name':'minecraft_prepare_region','arguments':{}}
    return t
