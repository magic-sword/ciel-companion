"""48 fixed real-model, recorded-action dialogue probes; never edits a world."""
import argparse
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace


def scenarios(include_regressions=False):
    rows=[]
    for group in range(6):
        for i in range(8):
            x=-12-i if i>=4 else 4+i
            coords=f'X={x}〜{x+1}、Y=64、Z=0〜1'
            r=dict(x1=x,x2=x+1,y1=64,y2=64,z1=0,z2=1)
            ref={'selection_id':'11111111-1111-4111-8111-111111111111','source':'owner_pointer',
                 'points':[{'x':x,'y':63,'z':z,'block':'grass_block','face':[0,1,0]} for z in (0,1)]}
            item={'id':f'g{group+1}-{i+1}','group':group,'split':'development'if i<4 else 'holdout',
                  'turns':[],'expected':{'operation':'floor','region':r,'block':'oak_planks'},'reference':None}
            if group==0:
                op=('clear','floor','wall','backfill')[i%4]
                if op=='wall':r['y2']=66;r['z2']=0
                if op=='backfill':r['y1']=61;r['y2']=63
                coords=f"X={r['x1']}〜{r['x2']}、Y={r['y1']}〜{r['y2']}、Z={r['z1']}〜{r['z2']}"
                instruction={'clear':'の土を全部取り除いて','floor':'にオークの板材で床を敷いて','wall':'にオークの板材で壁を建てて','backfill':'の穴をオークの板材で埋め戻して'}[op]
                item['turns']=[coords+instruction+'ください。'];item['expected']['operation']=op
                if op=='clear':item['expected'].pop('block')
            elif group==1:
                if i%4==0:item['turns']=[f'X={x}〜{x+1}、Z=0〜1にオークの板材で床を敷いてください。','Y=64です。']
                elif i%4==1:item['turns']=[coords+'に床を敷いてください。','材料はオークの板材です。']
                elif i%4==2:
                    item['turns']=[f'X={x}〜{x+1}、Y=64〜66にオークの板材で壁を建ててください。','Z=0の一面です。']
                    item['expected']={'operation':'wall','region':{**r,'y2':66,'z2':0},'block':'oak_planks'}
                else:
                    item['turns']=[f'X={x}〜{x+1}、Z=0〜1の穴を土で埋め戻してください。','底から仕上げまでY=61〜63です。']
                    item['expected']={'operation':'backfill','region':{**r,'y1':61,'y2':63},'block':'dirt'}
                item['expect_question']=True
            elif group==2:
                item['turns']=[coords+'、いやY=65にオークの板材で床を敷いてください。',
                               f'X={x}〜{x+1}、Y=65、Z=0〜1にオークの板材で床を敷いてください。']
                item['expected']['region']={**r,'y1':65,'y2':65};item['expect_question']=True
            elif group==3:
                item['turns']=[coords+('の土は取り除かないでください。'if i%2==0 else 'に床を作れますか？ まだ実行しないでください。')]
                item['expected']=None
            elif group==4:
                item['reference']=ref
                if i%4==0:item['turns']=[coords+'にオークの板材で床を敷いてください。']
                elif i%4==1:
                    item['turns']=['今選んだ地面の2点の上にオークの板材で床を敷いてください。']
                    item['expected']={'operation':'floor','selection_id':ref['selection_id'],'block':'oak_planks'}
                elif i%4==2:
                    item['reference']=None;item['turns']=['この2点の上にオークの板材で床を敷いてください。']
                    item['expected']=None;item['expect_question']=True
                else:
                    item['turns']=[coords+'にオークの板材で床を敷いてください。'];item['disconnect_on_prepare']=True
                    item['expected']=None
            else:
                item['turns']=[coords+'の土を全部除去し、Y=63の地面は残してください。']
                item['expected']={'operation':'clear','region':r,'preserve_regions':[{**r,'y1':63,'y2':63}]}
                if i%2:
                    item['refusal']='protected_block'if i%4==1 else 'missing_materials'
            rows.append(item)
    by_id={r['id']:r for r in rows}
    item=by_id['g1-5'];r=item['expected']['region']
    item['turns']=[f"X={r['x1']}〜{r['x2']}、Z=0〜1、残す地面Y=63、除去上限Y=65で土と石を取り除いて整地してください。"]
    item['expected']={'operation':'level','level':{'x1':r['x1'],'x2':r['x2'],'z1':0,'z2':1,'ground_y':63,'top_y':65}}
    item['expected']['clear_blocks']=['dirt','stone']
    retired=copy.deepcopy(item);retired.update(id='regression-level-1',split='development')
    item.update(id='g1-5-v2',turns=['上限Y=64、X=-23〜-21、地面Y=62、Z=-5〜-3の石だけを除去して整地してください。'],
        expected={'operation':'level','level':{'x1':-23,'x2':-21,'z1':-5,'z2':-3,'ground_y':62,'top_y':64},'clear_blocks':['stone']})
    item=by_id['g1-6'];r=item['expected']['region']
    item['turns']=[f"X={r['x2']}〜{r['x1']}、Y=64、Z=1〜0にオークの板材で床を敷いてください。"]
    item=by_id['g1-8'];r=item['expected']['region']
    item['turns'][0]='Ｘ='+str(r['x1'])+'〜'+str(r['x2'])+'、Ｙ=61〜63、Ｚ=0〜1の穴をオークの板材で埋め戻してください。'
    item=by_id['g4-3'];item['turns']=['「X=4〜5、Y=64、Z=0〜1に石の床を作って」は依頼文の例です。実行しないでください。']
    for name in ('g3-2','g3-4','g3-6','g3-8'):
        item=by_id[name];r=item['expected']['region'];r['y1']=r['y2']=64
        axes=f"X={r['x1']}〜{r['x2']}、Y=64、Z=0〜1"
        item['turns']=[axes+'に3×3のオークの板材の床を敷いてください。',axes+'に2×2のオークの板材の床を敷いてください。']
        item['expected']['expected_dimensions']=[2,2]
        item['clarify_first_prepare']=True
    item=by_id['g4-4'];r=item['expected']={'operation':'clear','region':dict(x1=7,x2=8,y1=65,y2=65,z1=2,z2=3)}
    item['turns']=['X=4〜5、Z=0〜1にオークの板材で床を作ってください。',
                   'その床の依頼は取り消します。別の依頼です。X=7〜8、Y=65、Z=2〜3の土だけを除去してください。']
    item['expect_question']=True
    item=by_id['g5-5'];item['turns']=['選んだ地面の2点の上にオークの板材で床を敷いてください。']
    item['expected']={'operation':'floor','selection_id':item['reference']['selection_id'],'block':'oak_planks'}
    for name in ('g6-4','g6-8'):
        item=by_id[name];r=item['expected']['region']
        item['turns']=[f"X={r['x1']}〜{r['x2']}、Y=64、Z=0〜1にガラスの床を敷いてください。材料不足なら着手せず中止してください。"]
        item['expected']={'operation':'floor','region':copy.deepcopy(r),'block':'glass'}
    for name in ('g6-3','g6-7'):
        item=by_id[name];r=item['expected']['region']
        saved=f"X={r['x1']}〜{r['x2']}、Y=64、Z=0〜1"if name=='g6-7'else 'Y=64'
        item['turns']=[f"X={r['x1']}〜{r['x2']}、Y=64、Z=0〜1の土を除去してください。ただし{saved}は保護して残してください。"]
        item['expected']['preserve_regions']=[copy.deepcopy(r)]
        item['refusal']='protected_overlap'
    by_id['g5-5']['refusal']='selection_expired'
    item=by_id['g5-6'];item['turns']=['選んだ2点のX/Z範囲を、地面Y=63を残し上限Y=65まで、土だけ取り除いて整地してください。']
    item['expected']={'operation':'level','selection_id':item['reference']['selection_id'],'level':{'ground_y':63,'top_y':65}}
    item=by_id['g5-7'];item['reference']=None;item['turns']=['X=-19〜-18、Z=0〜1に石の床を作ってください。','Y=64です。']
    item['other_speaker_before_reply']=True;item['expected']=None;item['expect_question']=True
    item=by_id['g5-8'];item['turns']=['選んだ地面の2点の上にオークの板材で床を敷いてください。']
    item.pop('disconnect_on_prepare',None);item['change_reference_after_select']=True
    item['expected']={'operation':'floor','selection_id':item['reference']['selection_id'],'block':'oak_planks'}
    for item in rows:
        if item['expected']and item['expected']['operation']in('clear','level'):
            item['expected'].setdefault('clear_blocks',['dirt'])
    return rows+[retired]if include_regressions else rows


def goal_spec(spec):
    """Independent effect equivalence: level and explicit clearing above ground."""
    s=copy.deepcopy(spec)
    if not s:return s
    if 'clear_blocks'in s:s['clear_blocks']=sorted(s['clear_blocks'])
    if s.get('operation')=='level'and 'selection_id'not in s:
        level=s.get('level',{})
        if all(k in level for k in ('x1','x2','z1','z2','ground_y','top_y'))and level['ground_y']<level['top_y']:
            region={k:level[k]for k in ('x1','x2','z1','z2')}
            region.update(y1=level['ground_y']+1,y2=level['top_y'])
            s.update(operation='clear',region=region,preserve_regions=[
                {**region,'y1':level['ground_y'],'y2':level['ground_y']},*s.get('preserve_regions',[])])
            s.pop('level')
    if s.get('preserve_regions'):
        unique={tuple(r[k]for k in ('x1','y1','z1','x2','y2','z2')):r for r in s['preserve_regions']}
        s['preserve_regions']=[unique[k]for k in sorted(unique)]
    return s


def canonical(name,args):
    if name=='minecraft_prepare_region':
        s=copy.deepcopy(args['spec']);s.pop('on_protected',None)
        if 'clear_blocks'in s:s['clear_blocks']=sorted(s['clear_blocks'])
        return goal_spec(s)
    if name in ('minecraft_clear_region','minecraft_build_region'):
        r={k:args[k]for k in ('x1','x2','y1','y2','z1','z2')}
        return {'operation':'clear'if name.endswith('clear_region')else 'floor'if r['y1']==r['y2']else 'wall',
                'region':r,**({'block':args['block']}if 'block'in args else {})}
    if name=='minecraft_pointed_action'and args.get('action')in('clear','floor'):
        return {'operation':args['action'],'selection_id':args['selection_id'],**({'block':args['block']}if 'block'in args else {})}
    return {'unexpected_tool':name,'arguments':args}


async def run(args):
    from .run import inference_server_info,provenance
    inference=await asyncio.to_thread(inference_server_info)
    source=Path('/stage1-baseline/agent')if args.variant=='baseline'else Path(__file__).resolve().parents[1]/'agent'
    sys.path.insert(0,str(source))
    os.environ['CIEL_LLM_BACKEND']='local'
    os.environ['CIEL_LOCAL_LLM_URL']=os.environ.get('CIEL_BENCH_LLM_URL','http://127.0.0.1:8094/v1')
    from game_env import GameEnv
    from game_intake import GameIntake
    from livekit.agents import llm
    catalog=GameEnv('minecraft','http://127.0.0.1:8773/mcp')
    rows=[]
    try:
        if not await catalog.prepare():raise RuntimeError('Dedicated catalog unavailable')
        cases=scenarios(include_regressions=bool(args.case))
        if args.group is not None:cases=cases[args.group*3:args.group*3+3]
        elif args.case:cases=[c for c in cases if c['id']in args.case]
        else:raise ValueError('Select at most three cases per 600-second run')
        if not 1<=len(cases)<=3:raise ValueError('Select one to three cases')
        run_started=time.monotonic()
        instructions=(source/'config/prompts/game_intake.md').read_text(encoding='utf-8')
        for case in cases:
            if time.monotonic()-run_started>=600:raise TimeoutError('Whole-run budget exhausted')
            calls=[];submits=[];replies=[];decisions=[]
            env=SimpleNamespace(profile=copy.deepcopy(catalog.profile),tools=list(catalog.tools),meta=copy.deepcopy(catalog.meta),
                playing=lambda:True,_connection_epoch=1,_body={},state={'references':copy.deepcopy(case['reference'])})
            async def refresh():return True
            env._refresh=refresh
            async def use(name,arguments):
                calls.append((name,copy.deepcopy(arguments)))
                if name=='minecraft_prepare_region'and case.get('clarify_first_prepare')and arguments.get('spec',{}).get('expected_dimensions')==[3,3]:
                    return {'status':'needs_clarification','reason':'dimension_mismatch',
                        'message':'座標から計算した寸法と指定寸法が一致しません。最終の範囲と寸法を指定してください。'}
                if case.get('disconnect_on_prepare'):env._connection_epoch+=1
                if case.get('refusal'):return {'status':'refused','reason':case['refusal'],
                    'message':{'protected_block':'保護対象があるため、施工を開始していません。','missing_materials':'材料不足です。必要4個、所持3個、あと1個です。',
                        'protected_overlap':'作業範囲と保護範囲が重なるため、施工を開始していません。',
                        'selection_expired':'選択の有効期限が切れたため、施工を開始していません。'}[case['refusal']]}
                return {'status':'ready','plan_id':'11111111-1111-4111-8111-111111111111'}if name=='minecraft_prepare_region'else {'status':'accepted'}
            async def start(name,arguments,**kwargs):
                submits.append((name,copy.deepcopy(arguments)))
                return {'task_id':'recorded-only','message':'作業を受け付けました。'}
            env.use=use
            runner=SimpleNamespace(env=env,work=None,status=lambda:{},body_step=lambda:None,start=start)
            select_prompt=source/'config/prompts/game_select.md'
            options={'select_instructions':select_prompt.read_text(encoding='utf-8')}if select_prompt.exists()else {}
            draft_prompt=source/'config/prompts/game_draft.md'
            if draft_prompt.exists():options['draft_instructions']=draft_prompt.read_text(encoding='utf-8')
            intake=GameIntake(runner,instructions,**options)
            infer=intake._infer
            async def capture(payload,started):
                value=await infer(payload,started)
                decisions.append({'stage':payload['stage'],'value':copy.deepcopy(value)})
                if payload['stage']=='select'and case.get('change_reference_after_select'):
                    env.state['references']={**copy.deepcopy(case['reference']),'selection_id':'22222222-2222-4222-8222-222222222222'}
                return value
            intake._infer=capture
            began=time.monotonic();failure=None
            try:
                async with asyncio.timeout(90):
                    for n,text in enumerate(case['turns']):
                        if n:
                            if calls and not case.get('clarify_first_prepare'):break
                            if case.get('expect_question')and not(replies[-1]and any(s in replies[-1]for s in ('？','?','教えて','指定','確認','選ん'))):break
                            if case.get('other_speaker_before_reply'):intake.on_transcribed(SimpleNamespace(),owner=False)
                            await asyncio.sleep(2)
                        reply=await intake.handle(llm.ChatMessage(id=case['id']+f'-{n}',role='user',content=[text]))
                        replies.append(reply)
            except Exception as exc:failure=type(exc).__name__
            finally:await intake.close()
            interpreted=[canonical(name,values)for name,values in calls]
            expected=goal_spec(case['expected'])
            errors=('依頼の操作を確認できませんでした。','作業の依頼を確認できませんでした。','操作の引数を確認できませんでした。')
            question=bool(replies and replies[0] and any(s in replies[0]for s in ('？','?','教えて','指定','確認','選ん')))
            passed=not failure and not any(reply in errors for reply in replies)
            if expected is None:
                passed=passed and not submits and (not calls or(case.get('disconnect_on_prepare',False)
                    and all(name=='minecraft_prepare_region'for name,_ in calls)))
            else:
                if case.get('clarify_first_prepare'):
                    first={**expected,'expected_dimensions':[3,3]}
                    passed=passed and interpreted in ([expected],[first,expected])
                else:passed=passed and interpreted==[expected]
                if args.variant=='candidate':passed=passed and len(submits)==(0 if case.get('refusal')else 1)
            if case.get('expect_question'):passed=passed and question
            row={'id':case['id'],'split':case['split'],'passed':bool(passed),'calls':calls,'submits':submits,'replies':replies,
                 'expected':case['expected'],'normalized_expected':expected,'decisions':decisions,'seconds':round(time.monotonic()-began,3),'error':failure,'semantic_review':'pending'}
            rows.append(row)
            print(json.dumps({'case':case['id'],'passed':bool(passed),'seconds':row['seconds'],'reply':replies if not passed else None},ensure_ascii=False),flush=True)
        report={'scope':'real_model_intake_recorded_actions_no_world_execution','suite':'spatial-stage1-intake-v2','variant':args.variant,
                'gate':'G1','gate_complete':False,'human_review':'pending',
                'intake_temperature':getattr(GameIntake,'LOCAL_TEMPERATURE',None),
                'inference_server':inference,'evaluator':provenance(),
                'group':args.group,'cases':rows,'fixture_sha256':hashlib.sha256(json.dumps(scenarios(),ensure_ascii=False).encode()).hexdigest(),
                'selected_fixture_sha256':hashlib.sha256(json.dumps(cases,ensure_ascii=False).encode()).hexdigest(),
                'source':{p:hashlib.sha256((source/p).read_bytes()).hexdigest()for p in ('game_intake.py','target_candidates.py','config/prompts/game_intake.md')}}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        return 0 if all(r['passed']for r in rows)else 1
    finally:await catalog.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant',choices=['baseline','candidate'],required=True)
    parser.add_argument('--group',type=int,choices=range(16))
    parser.add_argument('--case',action='append',default=[])
    parser.add_argument('--output',type=Path,required=True)
    raise SystemExit(asyncio.run(run(parser.parse_args())))
