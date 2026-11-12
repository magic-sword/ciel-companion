#!/usr/bin/env python3
"""Record development Minecraft deployment evidence without linking or moving a body."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('benchmark_home',Path(__file__).with_name('benchmark-home.py'))
home=importlib.util.module_from_spec(spec);spec.loader.exec_module(home)

REMOTE=r'''
from pathlib import Path
import subprocess,json,hashlib,time
root=Path.home()/'work/ciel-companion-dev/server'
dest=root/'data/deployments'/EVIDENCE
dest.mkdir(parents=True,exist_ok=True)
ids=subprocess.check_output(['docker','ps','-q','--filter','name=^ciel-'],text=True).split()
rows=json.loads(subprocess.check_output(['docker','inspect',*ids],text=True))
rows=[r for r in rows if not r['Name'].startswith('/ciel-minecraft-benchmark-')]
state={r['Name']:{'id':r['Id'],'image':r['Image'],'started_at':r['State']['StartedAt']}for r in rows}
if ACTION=='before':
    path=dest/'before.json'
    if path.exists():raise SystemExit('Before-state exists; refusing overwrite')
    path.write_text(json.dumps(state,indent=2));print('Saved before-state:',len(state),'services');raise SystemExit(0)
if (dest/'verification.json').exists():raise SystemExit('Verification exists; use a new evidence directory')
before=json.loads((dest/'before.json').read_text())
production={name:state.get(name)==value for name,value in before.items()if not name.startswith('/ciel-dev-')}
assert production,'No production before-state'
unexpected=set(state)-set(before)
sources={name:{'expected':digest,'actual':hashlib.sha256((root/name).read_bytes()).hexdigest()if(root/name).is_file()else None}for name,digest in EXPECTED.items()}
mismatches=[name for name,v in sources.items()if v['expected']!=v['actual']]
def python(container,code):
    return json.loads(subprocess.check_output(['docker','exec',container,'python','-c',code],text=True))
agent_files={name.removeprefix('agent/'):value for name,value in EXPECTED.items()if name in (
    'agent/agent.py','agent/persona.py','agent/game_intake.py','agent/target_candidates.py',
    'agent/config/persona.toml','agent/config/prompts/game_select.md','agent/config/prompts/game_intake.md','agent/config/prompts/game_draft.md')}
actual_agent=python('ciel-dev-agent-dev-1',"from pathlib import Path;import json,hashlib;print(json.dumps({p:hashlib.sha256(Path(p).read_bytes()).hexdigest()for p in "+repr(list(agent_files))+"}))")
body_files={name.removeprefix('minecraft/'):digest for name,digest in EXPECTED.items()if name.startswith('minecraft/src/')}
actual_body=json.loads(subprocess.check_output(['docker','exec',BODY_CONTAINER,'node','--input-type=module','-e',
    'import{readFileSync}from"node:fs";import{createHash}from"node:crypto";console.log(JSON.stringify(Object.fromEntries(JSON.parse(process.argv[1]).map(p=>[p,createHash("sha256").update(readFileSync(p)).digest("hex")]))));',json.dumps(list(body_files))],text=True))
mcp=python('ciel-dev-agent-dev-1',r"""import asyncio,json,os,hashlib
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from persona import load_persona
async def main():
 async with streamablehttp_client(os.environ['CIEL_GAMES'].split('=',1)[1])as(r,w,_):
  async with ClientSession(r,w)as session:
   await session.initialize()
   profile=json.loads((await session.read_resource('game://profile')).contents[0].text)
   names={t.name for t in(await session.list_tools()).tools}
   caps=profile['work']['capabilities']
   prep=next(c['preparation']for c in caps if c['name']=='minecraft.edit_region')
   persona=load_persona()
   loaded={name:hashlib.sha256(getattr(persona,'game_'+name+'_instructions').encode()).hexdigest()for name in('select','intake','draft')}
   print(json.dumps({'profile':profile['profile'],'work':profile['work']['version'],
    'capabilities':[c['name']for c in caps],'prepare_tool':'minecraft_prepare_region'in names,
    'old_api_present':bool(names&{'minecraft_clear_region','minecraft_build_region'}),
    'height_labels':prep.get('role_prefixes'),'variants':list(prep.get('variants',{})),
    'dev_target':os.getenv('CIEL_GAMES'),'loaded_intake_sha256':loaded,
    'runtime_settings':{key:os.getenv(key,'')for key in('CIEL_MODEL','CIEL_LLM_BACKEND','CIEL_INPUT','CIEL_STT_BACKEND')}}))
asyncio.run(main())""")
body_config=json.loads(subprocess.check_output(['docker','exec',BODY_CONTAINER,'node','-e',
    'console.log(JSON.stringify({owner_configured:Boolean(process.env.MC_OWNER),player_name:process.env.MC_USERNAME===process.argv[1],normal_world:process.env.MC_PORT==="25565"}))',PLAYER],text=True))
listing=subprocess.check_output(['docker','exec','ciel-minecraft-1','rcon-cli','list'],text=True)
containers={r['Name']:{'running':r['State']['Running'],'restarts':r['RestartCount']}for r in rows}
expected_loaded={name:hashlib.sha256((root/'agent/config/prompts'/('game_'+name+'.md')).read_text(encoding='utf-8').encode()).hexdigest()for name in('select','intake','draft')}
until=time.monotonic()+45
while True:
    started=json.loads(subprocess.check_output(['docker','inspect','ciel-dev-agent-dev-1'],text=True))[0]['State']['StartedAt']
    logs=subprocess.run(['docker','logs','--since',started,'ciel-dev-agent-dev-1'],capture_output=True,text=True)
    registered='registered worker'in(logs.stdout+logs.stderr).lower()
    if registered or time.monotonic()>=until:break
    time.sleep(1)
checks={'host_sources_match':not mismatches,'agent_image_sources_match':actual_agent==agent_files,
    'body_image_sources_match':actual_body==body_files if DEBUG_BODY else None,'production_unchanged':all(production.values()),
    'no_unexpected_services':not unexpected,'all_services_running':all(v['running']for v in containers.values()),
    'mcp_contract':mcp['profile']==2 and mcp['work']==1 and mcp['prepare_tool']and not mcp['old_api_present']and mcp['dev_target']=='minecraft='+TARGET,
    'loaded_intake_instructions_match':mcp['loaded_intake_sha256']==expected_loaded,
    'worker_registered':registered,
    'body_configuration':all(body_config.values()),'dev_player_connected':PLAYER in listing}
report={'checks':checks,'source_files':len(sources),'mismatches':mismatches,'production_unchanged':production,
    'unexpected_services':sorted(unexpected),'mcp':mcp,'body_configuration':body_config,'containers':containers,
    'agent_runtime_sha256':actual_agent,'body_runtime_sha256':actual_body}
(dest/'after.json').write_text(json.dumps(state,indent=2))
(dest/'source-files.json').write_text(json.dumps(sources,indent=2))
(dest/'verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps({'evidence':str(dest),'checks':checks,'source_files':len(sources)},indent=2))
raise SystemExit(0 if all(v for v in checks.values() if v is not None)else 1)
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['before','after'])
    parser.add_argument('--evidence',required=True,help='Unique directory name under development data/deployments')
    parser.add_argument('--debug-body',action='store_true',help='Verify explicitly launched Ciel_Debug on port 8775')
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,100}',args.evidence):parser.error('Invalid evidence directory name')
    expected={}
    if args.action=='after':
        for folder in (('agent','minecraft') if args.debug_body else ('agent',)):
            for path in sorted((ROOT/'server'/folder).rglob('*')):
                relative=path.relative_to(ROOT/'server')
                if path.is_file()and not path.is_symlink()and path.suffix in('.py','.js','.json','.md','.toml')and not any(p in('data','node_modules','__pycache__')for p in relative.parts):
                    expected[relative.as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    home.remote('DEBUG_BODY='+repr(args.debug_body)+'\nBODY_CONTAINER='+repr('ciel-dev-minecraft-body-dev-1' if args.debug_body else 'ciel-minecraft-body-1')
        +'\nPLAYER='+repr('Ciel_Debug' if args.debug_body else 'Ciel')+'\nTARGET='+repr('http://127.0.0.1:8775/mcp' if args.debug_body else 'http://127.0.0.1:8771/mcp')
        +'\nACTION='+repr(args.action)+'\nEVIDENCE='+repr(args.evidence)+'\nEXPECTED='+repr(expected)+'\n'+REMOTE)


if __name__=='__main__':main()
