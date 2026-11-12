"""Bounded single-reply recurrence probe; reconstructed log inputs, never game actions."""
import argparse
import json
from pathlib import Path
import re
import time
import httpx
from . import weight_space as w
from .repetition import renderer


def metrics(text, finish):
    cleaned = re.sub(r'\[[a-z_]+\]', '', text)
    sentences = [re.sub(r'\s+', '', s) for s in re.split(r'(?<=[。！？!?])|\n+', cleaned)]
    sentences = [s for s in sentences if len(s) >= 8]
    seen = set(); duplicate = []
    for s in sentences:
        if s in seen: duplicate.append(s)
        seen.add(s)
    longest = 1 if sentences else 0
    # Adjacent repeated blocks, including five-sentence loops; shortest units win ties.
    period = None
    for start in range(len(sentences)):
        for width in range(1, min(12, (len(sentences)-start)//2)+1):
            block = sentences[start:start+width]; cycles = 1
            while sentences[start+cycles*width:start+(cycles+1)*width] == block:
                cycles += 1
            if cycles > longest: longest, period = cycles, width
    total = sum(map(len, sentences)); repeated = sum(map(len, duplicate))
    return dict(chars=len(text),eligible_sentences=len(sentences),duplicate_sentences=len(duplicate),
                duplicate_chars=repeated,duplicate_fraction=repeated/total if total else None,
                literal_nonduplication_0_5=5*(1-repeated/total) if total else None,
                longest_cycles=longest,cycle_sentences=period,loop_observed=longest>=3,
                natural_stop=finish=='stop',censored=finish!='stop',
                quality_0_4=None,quality_evidence=None)


def reconstruct(rows, speech):
    end = next(i for i,r in enumerate(rows) if r.get('kind')=='speech' and r.get('id')==speech)
    prefix=rows[:end]
    instruction=next(r['instructions'] for r in reversed(prefix) if r.get('kind')=='reply_request')
    thought=next(r['text'] for r in reversed(prefix) if r.get('kind')=='thought_opening')
    history=[dict(role=r['role'],content=r['text']) for r in prefix
             if r.get('kind')=='item' and r.get('role') in ('user','assistant') and r.get('text')]
    return history,instruction,thought


def stream(payload, base, timeout, path):
    started=time.monotonic(); text=''; finish=None; usage={}; error=None; calls=[]
    with path.open('x',encoding='utf-8') as events:
        try:
            with httpx.Client(timeout=httpx.Timeout(timeout,read=min(timeout,60)),trust_env=False) as client:
                with client.stream('POST',base.rstrip('/')+'/chat/completions',
                    json={**payload,'stream':True,'stream_options':{'include_usage':True}},
                    headers={'X-Ciel-Work-Class':'foreground'}) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if time.monotonic()-started>timeout: raise TimeoutError('wall_deadline')
                        if not line.startswith('data:'): continue
                        data=line[5:].strip()
                        if data=='[DONE]': break
                        event=json.loads(data)
                        events.write(json.dumps(dict(elapsed=time.monotonic()-started,event=event),ensure_ascii=False)+'\n');events.flush()
                        usage=event.get('usage') or usage
                        for choice in event.get('choices',[]):
                            delta=choice.get('delta',{})
                            text+=delta.get('content') or ''
                            if delta.get('tool_calls'): calls.extend(delta['tool_calls'])
                            finish=choice.get('finish_reason') or finish
        except (httpx.HTTPError,TimeoutError,ValueError) as exc:
            error=type(exc).__name__+': '+str(exc)
    return dict(text=text,finish_reason=finish,error=error,tool_fragments=calls,usage=usage,
                elapsed=time.monotonic()-started,metrics=metrics(text,finish))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--log',type=Path,required=True);p.add_argument('--speech',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--agent-dir',type=Path,default=Path('/app'))
    p.add_argument('--base-url',default='http://127.0.0.1:8094/v1')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    rows=[json.loads(l) for l in a.log.read_text(encoding='utf-8').splitlines() if l.strip()]
    history,instruction,thought=reconstruct(rows,a.speech)
    render,source=renderer(a.agent_dir)
    system='\n'.join((a.agent_dir/'config/prompts'/f'{n}.md').read_text(encoding='utf-8') for n in w.PROMPTS)
    cases=[dict(id='incident-initiative',history=history,context=thought+'\n'+instruction,control=False),
           dict(id='topic-switch',history=history[:next(i for i in range(len(history)-1,-1,-1) if history[i]['role']=='user')+1],context='',control=False),
           dict(id='requested-repeat',history=[dict(role='user',content='発声練習です。「今日はいい天気ですね。」を8回、そのまま繰り返してください。')],context='',control=True)]
    before=w.probe('http://127.0.0.1:8095','/mode')
    if not before.get('ready') or before.get('mode')!='gpu': raise RuntimeError('Require ready shared GPU')
    report=dict(schema='ciel-within-reply-v1',reconstruction='approximate: recorded user/assistant items + initiative instruction; missing full system, tools, memory and event context',
        log_sha256=w.digest(a.log),runner_sha256=w.digest(__file__),renderer=source,
        before=before,props=w.probe(a.base_url.removesuffix('/v1'),'/props'),
        limits=dict(max_tokens=2048,stream_deadline_seconds=120,read_idle_seconds=60,max_wall_seconds_per_case=180),trials=[])
    report['observed_incident']=[dict(text=r['text'],metrics=metrics(r['text'],'stop' if r.get('done') else None))
        for r in rows if r.get('kind')=='mind_output' and r.get('speech')==a.speech]
    # Source completion is not proof of an EOS; the actual finish_reason was not logged.
    for r in report['observed_incident']:
        r['metrics']['natural_stop']=None;r['metrics']['censored']=None
    for i,c in enumerate(cases):
        # The initiative is an internal event, not a fabricated user utterance.
        messages=render(system,c['history']+([dict(role='system',content=c['context'])] if c['context'] else []),'')
        payload=dict(model='local',messages=messages,max_tokens=2048,seed=1729+i,
                     chat_template_kwargs={'enable_thinking':False})
        w.write(a.output/(c['id']+'-input.json'),payload)
        row=stream(payload,a.base_url,120,a.output/(c['id']+'-events.jsonl'))
        row.update(id=c['id'],control=c['control'],seed=1729+i)
        report['trials'].append(row);w.write(a.output/'report.json',report)
        print(json.dumps(dict(id=c['id'],**row['metrics']),ensure_ascii=False),flush=True)
    report['after']=w.probe('http://127.0.0.1:8095','/mode')
    report['mode_consistent']=report['after'].get('mode')==before['mode']
    w.write(a.output/'report.json',report)


if __name__=='__main__':main()
