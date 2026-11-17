#!/usr/bin/env python3
"""CLI for the independent search MCP service; never calls providers directly."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'server/agent'))
from research_service import request_search


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('query')
    parser.add_argument('--limit', type=int, choices=range(1, 6), default=3)
    parser.add_argument('--env-file', type=Path, default=ROOT / 'server/.env')
    parser.add_argument('--credentials-file', type=Path, default=ROOT / 'server/.env.shared')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error('output must be new')
    for key, path in [('CIEL_SEARCH_URL', args.env_file), ('CIEL_SEARCH_TOKEN', args.credentials_file)]:
        values = dotenv_values(path, interpolate=False) if path.is_file() else {}
        if key not in os.environ and values.get(key):
            os.environ[key] = values[key]
    try:
        result = asyncio.run(request_search(args.query, args.limit))
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'error': type(exc).__name__}))
        return 1
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf8') as stream:
            stream.write(encoded + '\n')
        print(json.dumps({'status': result['status'], 'results': len(result['results'])}))
    else:
        print(encoded)
    return 0 if result['status'] in ('ok', 'no_results') else 1


if __name__ == '__main__':
    sys.exit(main())
