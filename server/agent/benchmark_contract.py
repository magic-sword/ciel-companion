"""Benchmark dispatch contract, shared by the runner and the worker."""
import json
import re


def metadata(backend: str, model_id: str, trial: str) -> str:
    raw = json.dumps({'v':1,'type':'ciel.benchmark','backend':backend,'model_id':model_id,'trial':trial})
    validate(raw,backend,model_id)
    return raw


def validate(raw: str, backend: str, model_id: str) -> str:
    try:
        data = json.loads(raw)
    except (ValueError,TypeError):
        raise ValueError('Missing or invalid benchmark dispatch metadata') from None
    if (not isinstance(data,dict) or set(data) != {'v','type','backend','model_id','trial'}
            or type(data['v']) is not int or data['v'] != 1 or data['type'] != 'ciel.benchmark'
            or data['backend'] not in ('local','openai') or data['backend'] != backend
            or not isinstance(model_id,str) or not 1 <= len(model_id) <= 200 or data['model_id'] != model_id
            or not isinstance(data['trial'],str) or not re.fullmatch('[0-9a-f]{32}',data['trial'])):
        raise ValueError('Benchmark contract version, backend, model or trial mismatch')
    return data['trial']
