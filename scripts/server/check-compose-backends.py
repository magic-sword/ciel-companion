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
import json,os,subprocess,tempfile
from pathlib import Path
files=COMPOSE_SOURCES
results=[]
with tempfile.TemporaryDirectory(prefix='ciel-compose-check-') as folder:
    base=Path(folder)
    prod=base/'ciel-companion/server'
    dev=base/'ciel-companion-dev/server'
    prod.mkdir(parents=True);dev.mkdir(parents=True)
    shared='CIEL_DB_PASSWORD=fake-db\nLIVEKIT_API_KEY=fake-livekit\n'
    (prod/'.env.shared').write_text(shared)
    # Deliberately incompatible production settings must never reach dev.
    (prod/'.env').write_text('CIEL_LLM_BACKEND=local\nCIEL_INPUT=text\nCIEL_NOTES_MODEL=prod-only\nCIEL_MINUTES_DISCORD_WEBHOOK=https://prod.invalid\nCIEL_LOCAL_LLM_URL=http://127.0.0.1:9999/v1\n')
    cases=[('prod-default','prod',{},'openai',''),
      ('prod-local','prod',{'CIEL_LLM_BACKEND':'local'},'local',''),
      ('dev-default-isolated','dev',{},'openai',''),
      ('dev-local-voice','dev',{'CIEL_LLM_BACKEND':'local','CIEL_INPUT':'voice'},'local','voice'),
      ('dev-local-text','dev',{'CIEL_LLM_BACKEND':'local','CIEL_INPUT':'text'},'local','text'),
      ('prod-local-text','prod',{'CIEL_LLM_BACKEND':'local','CIEL_INPUT':'text'},'local','text'),
      ('dev-custom-model','dev',{'CIEL_LOCAL_LLM_MODEL':'custom-id','CIEL_VOSK_MODEL_PATH':'/models/custom-ja'},'openai',''),
      ('dev-webhook','dev',{'CIEL_MINUTES_DISCORD_WEBHOOK':'https://dev.invalid'},'openai',''),
      ('prod-webhook','prod',{'CIEL_MINUTES_DISCORD_WEBHOOK':'https://own.invalid'},'openai',''),
      ('dev-custom-notes','dev',{'CIEL_NOTES_MODEL':'dev-notes'},'openai',''),
      ('dev-empty-roles','dev',{'CIEL_LOCAL_ROLES':''},'openai',''),
      ('dev-whisper','dev',{'CIEL_LLM_BACKEND':'local','CIEL_INPUT':'voice','CIEL_STT_BACKEND':'whisper','CIEL_WHISPER_MODEL_PATH':'/models-whisper/small'},'local','voice'),
      ('prod-whisper','prod',{'CIEL_LLM_BACKEND':'local','CIEL_INPUT':'voice','CIEL_STT_BACKEND':'whisper','CIEL_WHISPER_MODEL_PATH':'/models-whisper/small'},'local','voice')]
    env={k:v for k,v in os.environ.items() if not k.startswith(('CIEL_','LOCAL_LLM_','COMPOSE_','LIVEKIT_','OPENAI_','YOUTUBE_'))}
    for name,kind,settings,backend,mode in cases:
        if kind=='dev':
            (prod/'.env').write_text('CIEL_LLM_BACKEND=local\nCIEL_INPUT=text\nCIEL_NOTES_MODEL=prod-only\nCIEL_MINUTES_DISCORD_WEBHOOK=https://prod.invalid\nCIEL_LOCAL_LLM_URL=http://127.0.0.1:9999/v1\n')
        root=prod if kind=='prod' else dev
        config=root/('.env' if kind=='prod' else '.env.dev')
        config.write_text(''.join(k+'='+v+'\n' for k,v in settings.items()))
        command=['docker','compose','--project-directory',str(root),'--env-file',str(prod/'.env.shared'),'--env-file',str(config),'-f','-','config','--format','json']
        result=subprocess.run(command,input=files[kind],cwd=root,env=env,capture_output=True,text=True)
        if result.returncode:raise RuntimeError('Compose validation failed: '+name+'\n'+result.stderr)
        service=json.loads(result.stdout)['services']['agent' if kind=='prod' else 'agent-dev']
        values=service['environment']
        assert values['CIEL_LLM_BACKEND']==backend,name
        assert values['CIEL_INPUT']==mode,name
        assert values['CIEL_LOCAL_LLM_URL']=='http://127.0.0.1:8094/v1',name
        assert values['CIEL_LOCAL_LLM_MODEL']==settings.get('CIEL_LOCAL_LLM_MODEL','local'),name
        assert values['CIEL_VOSK_MODEL_PATH']==settings.get('CIEL_VOSK_MODEL_PATH','/models/vosk-model-small-ja-0.22'),name
        assert values['CIEL_MINUTES_DISCORD_WEBHOOK']==settings.get('CIEL_MINUTES_DISCORD_WEBHOOK',''),name
        assert values.get('CIEL_NOTES_MODEL')==settings.get('CIEL_NOTES_MODEL'),name
        assert values['LIVEKIT_API_KEY']=='fake-livekit',name
        assert values['CIEL_MEMORY_SCOPE']==('main' if kind=='prod' else 'dev'),name
        assert not any(k.startswith('CIEL_DEV_') for k in values),name
        mount=next(v for v in service['volumes'] if v['target']=='/models')
        assert mount['read_only'],name
        whisper=next(v for v in service['volumes'] if v['target']=='/models-whisper')
        assert whisper['read_only'],name
        assert values['CIEL_WHISPER_MODEL_PATH']==settings.get('CIEL_WHISPER_MODEL_PATH','/models-whisper/small'),name
        assert values['CIEL_STT_BACKEND']==settings.get('CIEL_STT_BACKEND',''),name
        results.append({'case':name,'backend':backend,'input':mode or 'voice (default)','isolated':True})
    (dev/'compose.dev.yaml').write_text(files['dev'])
    (dev/'compose.livekit-local.yaml').write_text(files['livekit'])
    (dev/'.env.dev').write_text('CIEL_LLM_BACKEND=local\nCIEL_OPENAI_ROLES=\nCIEL_MIND_MODEL=dev-model\nCIEL_MIND_REASONING=high\n')
    for roles,model in [('mind','gpt-5.4-mini'),('','local')]:
        local=dev/'.env.livekit-local'
        local.write_text('LIVEKIT_LOCAL_BIND=127.0.0.1\nLIVEKIT_LOCAL_KEY=test\nLIVEKIT_LOCAL_SECRET=fake-secret\nCIEL_LOCAL_AGENT_IMAGE=test-image\nCIEL_LOCAL_AGENT_CONFIG='+str(dev/'agent/config')+'\nCIEL_OPENAI_ROLES='+roles+'\nCIEL_MIND_MODEL='+model+'\nCIEL_MIND_REASONING=none\n')
        command=['docker','compose','--env-file',str(prod/'.env.shared'),'--env-file',str(dev/'.env.dev'),'--env-file',str(local),'-f','compose.dev.yaml','-f','compose.livekit-local.yaml','config','--format','json']
        result=subprocess.run(command,cwd=dev,env=env,capture_output=True,text=True,check=True)
        values=json.loads(result.stdout)['services']['agent-local']['environment']
        assert values['LIVEKIT_URL']=='ws://127.0.0.1:7880' and values['LIVEKIT_API_KEY']=='test'
        assert values['CIEL_LLM_BACKEND']=='local' and values['CIEL_OPENAI_ROLES']==roles
        assert values['CIEL_MIND_MODEL']==model and values['CIEL_MIND_REASONING']=='none'
        assert values['CIEL_MEMORY_SCOPE']=='dev'
        results.append({'case':'local-livekit-'+('openai-mind' if roles else 'local-mind'),'isolated':True})
    (prod/'compose.yaml').write_text(files['prod'])
    (prod/'compose.livekit-production.yaml').write_text(files['production_livekit'])
    (prod/'.env.livekit-production').write_text('LIVEKIT_LOCAL_BIND=127.0.0.1\nLIVEKIT_LOCAL_KEY=local-key\nLIVEKIT_LOCAL_SECRET=local-secret\n')
    (prod/'.env').write_text('CIEL_LLM_BACKEND=local\nCIEL_OPENAI_ROLES=mind\nCIEL_MIND_MODEL=gpt-5.4-mini\n')
    command=['docker','compose','--env-file','.env.shared','--env-file','.env.livekit-production','--env-file','.env','-f','compose.yaml','-f','compose.livekit-production.yaml','config','--format','json']
    result=subprocess.run(command,cwd=prod,env=env,capture_output=True,text=True,check=True)
    service=json.loads(result.stdout)['services']['agent'];values=service['environment']
    assert values['LIVEKIT_URL']=='ws://127.0.0.1:7880' and values['LIVEKIT_API_KEY']=='local-key'
    assert values['CIEL_AGENT_NAME']=='ciel-main' and values['CIEL_MEMORY_SCOPE']=='main'
    assert values['CIEL_OPENAI_ROLES']=='mind' and values['CIEL_MIND_MODEL']=='gpt-5.4-mini'
    assert next(v for v in service['volumes'] if v['target']=='/app/config')['source']==str(prod/'agent/config')
    results.append({'case':'production-local-livekit-main-scope','isolated':True})
print(json.dumps({'status':'passed','checks':results,'services_restarted':False},ensure_ascii=False))
"""
if __name__=='__main__':
    sources={'prod':(ROOT/'server/compose.yaml').read_text(encoding='utf-8'),'dev':(ROOT/'server/compose.dev.yaml').read_text(encoding='utf-8')}
    sources['livekit']=(ROOT/'server/compose.livekit-local.yaml').read_text(encoding='utf-8')
    sources['production_livekit']=(ROOT/'server/compose.livekit-production.yaml').read_text(encoding='utf-8')
    home.remote(CODE.replace('COMPOSE_SOURCES',repr(sources)))
