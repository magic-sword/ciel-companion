#!/usr/bin/env python3
"""Read-only: validate production/dev Compose settings on the configured Linux server.

No service is built or restarted; resolved credentials are never printed or saved.
"""
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('benchmark_home',Path(__file__).with_name('benchmark-home.py'))
home=importlib.util.module_from_spec(spec);spec.loader.exec_module(home)
CODE=r"""
import json,os,subprocess
from pathlib import Path
base=Path.home()/'work'
files=COMPOSE_SOURCES
fields=['CIEL_LLM_BACKEND','CIEL_INPUT','CIEL_STT_BACKEND','CIEL_VOSK_MODEL_PATH',
 'CIEL_VOSK_MODELS_DIR','CIEL_LOCAL_LLM_URL','CIEL_LOCAL_LLM_MODEL','CIEL_LOCAL_TIMEOUT',
 'CIEL_DEV_LLM_BACKEND','CIEL_DEV_INPUT','CIEL_DEV_STT_BACKEND','CIEL_DEV_VOSK_MODEL_PATH',
 'CIEL_DEV_VOSK_MODELS_DIR','CIEL_DEV_LOCAL_LLM_URL','CIEL_DEV_LOCAL_LLM_MODEL','CIEL_DEV_LOCAL_TIMEOUT']
cases=[
 ('prod-default','prod',{},'openai','', 'http://127.0.0.1:8094/v1'),
 ('prod-local','prod',{'CIEL_LLM_BACKEND':'local'},'local','', 'http://127.0.0.1:8094/v1'),
 ('dev-does-not-inherit-prod','dev',{'CIEL_LLM_BACKEND':'local','CIEL_LOCAL_LLM_URL':'http://127.0.0.1:9999/v1'},'openai','', 'http://127.0.0.1:8094/v1'),
 ('dev-local','dev',{'CIEL_LLM_BACKEND':'openai','CIEL_DEV_LLM_BACKEND':'local','CIEL_DEV_INPUT':'voice'},'local','voice','http://127.0.0.1:8094/v1'),
 ('prod-local-text','prod',{'CIEL_LLM_BACKEND':'local','CIEL_INPUT':'text'},'local','text','http://127.0.0.1:8094/v1'),
 ('prod-custom-model','prod',{'CIEL_LLM_BACKEND':'local','CIEL_VOSK_MODEL_PATH':'/models/custom-ja','CIEL_VOSK_MODELS_DIR':str(Path.home()/'models/custom-vosk')},'local','', 'http://127.0.0.1:8094/v1'),
 ('dev-custom-model','dev',{'CIEL_DEV_LLM_BACKEND':'local','CIEL_DEV_VOSK_MODEL_PATH':'/models/dev-ja'},'local','', 'http://127.0.0.1:8094/v1'),
]
results=[]
for name,kind,overrides,backend,mode,url in cases:
    root=base/('ciel-companion/server' if kind=='prod' else 'ciel-companion-dev/server')
    env={**os.environ,**{field:'' for field in fields},**overrides}
    command=['docker','compose','--project-directory',str(root),'--env-file',str(base/'ciel-companion/server/.env'),'-f','-','config','--format','json']
    result=subprocess.run(command,input=files[kind],cwd=root,env=env,capture_output=True,text=True)
    if result.returncode:raise RuntimeError('Compose validation failed: '+name)
    service=json.loads(result.stdout)['services']['agent' if kind=='prod' else 'agent-dev']
    values=service['environment']
    assert values['CIEL_LLM_BACKEND']==backend,name
    assert values['CIEL_INPUT']==mode,name
    assert values['CIEL_LOCAL_LLM_URL']==url,name
    mount=next(v for v in service['volumes'] if v['target']=='/models')
    assert mount['read_only'],name
    if name=='prod-custom-model':
        assert values['CIEL_VOSK_MODEL_PATH']=='/models/custom-ja' and mount['source']==str(Path.home()/'models/custom-vosk')
    elif name=='dev-custom-model':assert values['CIEL_VOSK_MODEL_PATH']=='/models/dev-ja'
    else:assert values['CIEL_VOSK_MODEL_PATH']=='/models/vosk-model-small-ja-0.22'
    results.append({'case':name,'backend':backend,'input':mode or 'voice (default)','model_mount_readonly':True})
print(json.dumps({'status':'passed','checks':results,'services_restarted':False},ensure_ascii=False))
"""
if __name__=='__main__':
    sources={'prod':(ROOT/'server/compose.yaml').read_text(encoding='utf-8'),'dev':(ROOT/'server/compose.dev.yaml').read_text(encoding='utf-8')}
    home.remote(CODE.replace('COMPOSE_SOURCES',repr(sources)))
