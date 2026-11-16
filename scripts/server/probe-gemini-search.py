#!/usr/bin/env python3
"""Bounded Gemini 2.5 Flash-Lite Google Search trial; no deployment or fallback.

--check-config makes no network requests. --run requires the operator to confirm
the project's Free Tier; an API key does not reveal or enforce its billing tier.
"""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
MODEL = 'gemini-2.5-flash-lite'
ENDPOINT = f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent'
QUESTIONS = [
    'Python公式サイトをGoogle検索し、現在の最新安定版のバージョンとリリース日を、公式の出典付きで確認してください。',
    'Google公式資料を検索し、Custom Search JSON APIの新規利用可否と提供終了予定日を確認してください。',
    'Gemini公式資料を検索し、gemini-2.5-flash-liteのGoogle検索連携の無料枠を、利用条件とともに確認してください。',
]


def inspect_grounding(data):
    candidate = (data.get('candidates') or [{}])[0]
    text = '\n'.join(p['text'] for p in candidate.get('content', {}).get('parts', [])
                     if isinstance(p.get('text'), str) and not p.get('thought')).strip()
    metadata = candidate.get('groundingMetadata') or {}
    sources = []
    valid_indices = set()
    for index, chunk in enumerate(metadata.get('groundingChunks') or []):
        web = chunk.get('web') or {}
        url = web.get('uri', '')
        try:
            parsed = urlsplit(url)
            valid = (parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username
                     and not parsed.password and not any(ord(c) < 32 for c in url))
        except ValueError:
            valid = False
        if valid:
            valid_indices.add(index)
            sources.append(dict(index=index, title=web.get('title', ''), url=url))
    supports = [s for s in metadata.get('groundingSupports') or []
                if (s.get('segment') or {}).get('text') and
                any(i in valid_indices for i in s.get('groundingChunkIndices') or [])]
    version = data.get('modelVersion', '')
    grounded = (version.startswith(MODEL) and candidate.get('finishReason') == 'STOP' and bool(text)
                and bool(metadata.get('webSearchQueries')) and bool(sources) and bool(supports))
    return dict(grounding_present=grounded, model_version=version, finish_reason=candidate.get('finishReason'),
                text=text, queries=metadata.get('webSearchQueries', []), sources=sources,
                support_count=len(supports), search_suggestions_present=bool(metadata.get('searchEntryPoint')),
                usage=data.get('usageMetadata', {}))


def run(args):
    env = dotenv_values(args.env_file) if args.env_file.is_file() else {}
    key = os.environ.get('GEMINI_API_KEY') or env.get('GEMINI_API_KEY')
    if args.check_config:
        print(json.dumps(dict(model=MODEL, key_present=bool(key), billing_tier='not_determined', requests=0)))
        return 0
    if not args.free_tier_confirmed:
        raise ValueError('Confirm the project is on Free Tier before using --free-tier-confirmed; no request sent')
    if not key:
        raise ValueError('Set GEMINI_API_KEY in the environment or --env-file; no request sent')
    if args.output is None:
        raise ValueError('--output is required for --run')
    if args.output.exists():
        raise ValueError('Output must be new')
    instructions_path = ROOT / 'server/agent/config/prompts/research.md'
    instructions = instructions_path.read_text(encoding='utf8')
    now = datetime.now(timezone(timedelta(hours=9))).isoformat()
    report = dict(model=MODEL, endpoint=ENDPOINT, requested_at=now, free_tier_operator_confirmed=True,
                  billing_verified_by_api=False, max_requests=args.limit, max_output_tokens=1600,
                  instructions_sha256=hashlib.sha256(instructions_path.read_bytes()).hexdigest(),
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), trials=[])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=45, follow_redirects=False) as client:
        for question in QUESTIONS[:args.limit]:
            body = dict(systemInstruction={'parts': [{'text': instructions}]},
                        contents=[{'role': 'user', 'parts': [{'text': json.dumps(dict(
                            question=question, requested_at=now), ensure_ascii=False)}]}],
                        tools=[{'google_search': {}}], generationConfig={'maxOutputTokens': 1600, 'temperature': 0})
            row = dict(question=question)
            started = time.monotonic()
            try:
                response = client.post(ENDPOINT, headers={'x-goog-api-key': key}, json=body)
                row['http_status'] = response.status_code
                data = response.json()
                row['response'] = data
                if response.status_code == 200:
                    row.update(inspect_grounding(data))
                else:
                    row['grounding_present'] = False
                    row['error'] = (data.get('error') or {}).get('status', 'http_error')
            except (httpx.HTTPError, ValueError) as exc:
                row.update(grounding_present=False, error=type(exc).__name__)
            row['seconds'] = round(time.monotonic() - started, 3)
            report['trials'].append(row)
            # Keep the original evidence, including citation mappings and search
            # suggestions, but never persist credentials, even in an echoed error.
            encoded = json.dumps(report, ensure_ascii=False, indent=2).replace(key, '[REDACTED]')
            args.output.write_text(encoded, encoding='utf8')
            print(json.dumps({k: row.get(k) for k in ('http_status', 'grounding_present', 'model_version', 'error', 'seconds')}))
            if not row['grounding_present']:
                return 1  # No retries, fallback model, or second question after a failure.
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-config', action='store_true')
    mode.add_argument('--run', action='store_true')
    parser.add_argument('--env-file', type=Path, default=ROOT / 'scripts/server/.env.local')
    parser.add_argument('--free-tier-confirmed', action='store_true')
    parser.add_argument('--limit', type=int, choices=(1, 2, 3), default=1)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        sys.exit(run(args))
    except ValueError as exc:
        parser.error(str(exc))
