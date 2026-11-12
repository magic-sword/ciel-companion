"""Development-only HTTP-boundary inference evidence; never log credentials/headers."""
import contextvars
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid
import contextlib
import httpx
import debug_log

correlation = contextvars.ContextVar('inference_trace', default={})
FILE_LIMIT = 16 * 1024 * 1024
TOTAL_LIMIT = 256 * 1024 * 1024
EVENT_LIMIT = 2 * 1024 * 1024
_disabled = set()
_clients = []
SECRET = re.compile(r'^(authorization|.*api[_-]?key|.*secret|.*password|access_token|refresh_token|device_token|token|cookie)$', re.I)


@contextlib.contextmanager
def quota_lock(folder):
    with (folder/'.quota.lock').open('a+b') as f:
        if os.name=='nt':
            import msvcrt
            f.write(b'0');f.flush();f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_LOCK,1)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX)
        try:yield
        finally:
            if os.name=='nt':
                f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f,fcntl.LOCK_UN)


def enabled():
    return os.getenv('CIEL_AGENT_NAME') == 'ciel-dev' and os.getenv('CIEL_INFERENCE_TRACE') == '1'


def redact(value):
    if isinstance(value, dict):
        return {k: '[REDACTED]' if SECRET.fullmatch(k) else redact(v) for k,v in value.items()}
    if isinstance(value, list): return [redact(v) for v in value]
    if isinstance(value, str):
        if value.startswith('data:'): return '[OMITTED_INLINE_DATA]'
        try:
            parsed=json.loads(value)
            if isinstance(parsed,(dict,list)):
                clean=redact(parsed)
                return json.dumps(clean,ensure_ascii=False) if clean!=parsed else value
        except (ValueError,TypeError): pass
        for key,secret in os.environ.items():
            if SECRET.fullmatch(key) and len(secret)>=8: value=value.replace(secret,'[REDACTED]')
        return re.sub(r'(?i)Bearer\s+[A-Za-z0-9._~-]+','Bearer [REDACTED]',value)
    return value


def write(kind, **data):
    if not enabled() or debug_log._path is None: return False
    path=debug_log._path.parent/'traces'/debug_log._path.name
    if str(path) in _disabled: return False
    try:
        path.parent.mkdir(mode=0o700,exist_ok=True)
        with quota_lock(path.parent):return append(path,kind,data)
    except (OSError,ValueError,TypeError):
        return False


def append(path,kind,data):
    try:
        safe=redact(data)
        encoded=(json.dumps(dict(t=time.time(),kind=kind,**safe),ensure_ascii=False,default=str)+'\n').encode()
        size=path.stat().st_size if path.exists() else 0
        total=sum(p.stat().st_size for p in path.parent.glob('*.jsonl'))
        if len(encoded)>EVENT_LIMIT or size+len(encoded)>FILE_LIMIT-1024 or total+len(encoded)>TOTAL_LIMIT-1024:
            _disabled.add(str(path))
            encoded=(json.dumps(dict(t=time.time(),kind='trace_incomplete',reason='size_limit',
                request_id=data.get('request_id'),speech_id=data.get('speech_id')))+'\n').encode()
            if size+len(encoded)>FILE_LIMIT or total+len(encoded)>TOTAL_LIMIT:return False
        fd=os.open(path,os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
        with os.fdopen(fd,'ab') as f:f.write(encoded)
        return str(path) not in _disabled
    except (OSError,ValueError,TypeError):
        return False  # Diagnostics cannot break conversation.


class Stream(httpx.AsyncByteStream):
    def __init__(self, inner, ids):
        self.inner=inner;self.ids=ids;self.buffer=b'';self.done=False;self.seq=0

    async def __aiter__(self):
        try:
            async for chunk in self.inner:
                self.buffer+=chunk
                if len(self.buffer)>EVENT_LIMIT:
                    write('trace_incomplete',**self.ids,reason='stream_line_limit');self.buffer=b''
                while b'\n' in self.buffer:
                    line,self.buffer=self.buffer.split(b'\n',1)
                    if not line.startswith(b'data:'):continue
                    body=line[5:].strip()
                    if body==b'[DONE]':self.done=True
                    else:
                        try:
                            event=json.loads(body)
                            write('llm_event',**self.ids,seq=self.seq,event=event);self.seq+=1
                        except ValueError:write('trace_incomplete',**self.ids,reason='invalid_event')
                yield chunk
        finally:
            write('llm_stream_end',**self.ids,done_marker=self.done,events=self.seq,
                  trailing_bytes=len(self.buffer))

    async def aclose(self):await self.inner.aclose()


class Transport(httpx.AsyncBaseTransport):
    def __init__(self, inner=None):
        self.inner=inner or httpx.AsyncHTTPTransport();self.runtime=None;self.runtime_at=0

    async def metadata(self):
        if time.monotonic()-self.runtime_at<60:return self.runtime
        values={'captured_at':time.time()}
        async with httpx.AsyncClient(timeout=2,trust_env=False) as client:
            for key,url in [('mode',os.getenv('CIEL_LOCAL_LLM_CONTROL','http://127.0.0.1:8095')+'/mode'),
                            ('props',os.getenv('CIEL_LOCAL_LLM_URL','http://127.0.0.1:8094/v1').removesuffix('/v1')+'/props')]:
                try:
                    r=await client.get(url);r.raise_for_status();values[key]=r.json()
                except (httpx.HTTPError,ValueError):values[key]={'unavailable':True}
        self.runtime=values;self.runtime_at=time.monotonic();return values

    async def handle_async_request(self, request):
        if not enabled() or not request.url.path.endswith('/chat/completions'):
            return await self.inner.handle_async_request(request)
        ids={**correlation.get(),'http_id':uuid.uuid4().hex}
        try:
            payload=json.loads(request.content)
            safe=redact(payload)
            write('llm_request',**ids,payload=safe,redacted=safe!=payload,
                  payload_sha256=hashlib.sha256(request.content).hexdigest(),
                  endpoint_path=request.url.path,host=request.url.host,
                  runtime_manifest=os.getenv('CIEL_TRACE_RUNTIME_MANIFEST','unavailable'),runtime=await self.metadata())
        except (ValueError,httpx.RequestNotRead):write('trace_incomplete',**ids,reason='unreadable_request')
        try:
            response=await self.inner.handle_async_request(request)
        except BaseException as exc:
            write('llm_transport_end',**ids,error=type(exc).__name__);raise
        write('llm_response',**ids,status=response.status_code)
        if 'text/event-stream' in response.headers.get('content-type',''):
            response.stream=Stream(response.stream,ids)
        else:write('trace_incomplete',**ids,reason='non_stream_response')
        return response

    async def aclose(self):await self.inner.aclose()


def client_options():
    if not enabled():return {}
    import openai
    client=openai.AsyncOpenAI(base_url=os.environ.get('CIEL_LOCAL_LLM_URL','http://127.0.0.1:8094/v1'),
        api_key='local',max_retries=0,http_client=httpx.AsyncClient(transport=Transport(),
        timeout=httpx.Timeout(float(os.getenv('CIEL_LOCAL_TIMEOUT','90'))),trust_env=False))
    _clients.append(client)
    return {'client':client}


async def close_clients():
    while _clients:await _clients.pop().close()


def export_request(path, http_id):
    rows=[json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    request=next(r for r in rows if r.get('kind')=='llm_request' and r.get('http_id')==http_id)
    if request['redacted']:raise ValueError('Redacted input cannot be exported as exact replay')
    if any(r.get('kind')=='trace_incomplete' and r['t']>=request['t'] for r in rows):
        raise ValueError('Trace incomplete; retain as partial evidence, not exact replay')
    return request['payload']


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description='Export captured HTTP payload without executing model/tools')
    p.add_argument('--trace',type=Path,required=True);p.add_argument('--http-id',required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    value=export_request(a.trace,a.http_id)
    with a.output.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)


def export_request(path, http_id):
    rows=[json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    request=next(r for r in rows if r.get('kind')=='llm_request' and r.get('http_id')==http_id)
    if request['redacted']:raise ValueError('Redacted input cannot be exported as exact replay')
    if any(r.get('kind')=='trace_incomplete' and r['t']>=request['t'] for r in rows):
        raise ValueError('Trace incomplete; retain as partial evidence, not exact replay')
    return request['payload']


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description='Export captured HTTP payload without executing model/tools')
    p.add_argument('--trace',type=Path,required=True);p.add_argument('--http-id',required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    value=export_request(a.trace,a.http_id)
    with a.output.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
