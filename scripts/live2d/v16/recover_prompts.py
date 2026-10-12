"""Read only the preceding v16 session's image generation calls for provenance."""
import json
from pathlib import Path

source = Path('C:/Users/prog/.codex/sessions/2026/10/12/rollout-2026-10-12T08-57-07-01a12d66-1687-7bc0-9749-d6fe4d665bc8.jsonl')
records = []
for line in source.open(encoding='utf-8'):
    row = json.loads(line)
    payload = row.get('payload', {})
    if not isinstance(payload, dict):
        continue
    name = payload.get('name', '')
    args = payload.get('arguments', payload.get('input', ''))
    if payload.get('type') in ('function_call', 'custom_tool_call') and ('imagegen' in args or 'imagegen' in name or '_prompt_' in args):
        records.append({'timestamp': row.get('timestamp'), 'name': name, 'arguments': args})
target = Path('assets/ciel/generated/v16/prior-generation-calls.json')
with target.open('w', encoding='utf-8') as out:
    json.dump(records, out, ensure_ascii=False, indent=2)
print(json.dumps(records, ensure_ascii=True, indent=2))
