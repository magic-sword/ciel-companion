#!/usr/bin/env python3
"""One read-only search of a reviewed API. Never crawl result links or follow redirects."""
import argparse
import asyncio
from datetime import date, datetime, timezone
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values

REGISTRY = Path(__file__).with_name('config') / 'search-sources.json'
DEFAULT_ENV = Path(__file__).with_name('.env')
ENDPOINTS = {
    'wikipedia-ja': 'https://ja.wikipedia.org/w/api.php',
    'wikipedia-en': 'https://en.wikipedia.org/w/api.php',
}


def source_policy(source, registry=REGISTRY, today=None):
    data = json.loads(registry.read_text(encoding='utf8'))
    policy = data.get('sources', {}).get(source)
    if data.get('version') != 1 or source not in ENDPOINTS or not policy:
        raise ValueError('unapproved_source')
    if policy.get('endpoint') != ENDPOINTS[source] or policy.get('scope') != 'search_snippets_only':
        raise ValueError('unapproved_endpoint_or_scope')
    today = today or date.today()
    if not date.fromisoformat(policy['reviewed_on']) <= today < date.fromisoformat(policy['review_before']):
        raise ValueError('policy_review_required')
    for field in ('permission_url', 'api_url', 'terms_url', 'license_url'):
        parsed = urlsplit(policy.get(field, ''))
        if parsed.scheme != 'https' or not parsed.hostname:
            raise ValueError('missing_policy_evidence')
    if not policy.get('permission_basis'):
        raise ValueError('missing_policy_evidence')
    return policy


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain(text):
    parser = PlainText()
    parser.feed(text)
    return ' '.join(''.join(parser.parts).split())[:1200]


async def async_search(source, query, limit, contact, *, transport=None, registry=REGISTRY):
    policy = source_policy(source, registry)
    if not 1 <= len(query.strip()) <= 600 or not 1 <= limit <= 10:
        raise ValueError('invalid_query_or_limit')
    # Contact is an operator-supplied public URL or email, not a secret or API key.
    if (not contact or len(contact) > 200 or not contact.isascii() or
            any(ord(c) < 33 for c in contact) or '(' in contact or ')' in contact or
            not (contact.startswith('https://') or '@' in contact)):
        raise ValueError('operator_contact_required')
    report = dict(source=source, query=query.strip(), status='failed', results=[],
                  retrieved_at=datetime.now(timezone.utc).isoformat(),
                  content_kind='search_snippets', pages_fetched=False,
                  untrusted_content=True, policy=policy)
    params = dict(action='query', list='search', srsearch=query.strip(), srnamespace=0,
                  srlimit=limit, srprop='snippet', format='json', formatversion=2, maxlag=5)
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False, transport=transport,
                          headers={'User-Agent': f'CielApprovedSearch/1.0 ({contact})'}) as client:
            async with client.stream('GET', policy['endpoint'], params=params) as response:
                report['http_status'] = response.status_code
                if response.status_code != 200:
                    report['status'] = ('rate_limited' if response.status_code == 429 else
                                        'redirect_refused' if 300 <= response.status_code < 400 else 'http_error')
                    report['retry_after'] = response.headers.get('Retry-After')
                    return report
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 1_000_000:
                        report['status'] = 'response_too_large'
                        return report
                data = json.loads(body)
        if 'error' in data:
            report['status'] = 'api_error'
            report['retry_after'] = response.headers.get('Retry-After')
            return report
        rows = data['query']['search']
        if not isinstance(rows, list):
            raise ValueError('invalid_response')
        host = urlsplit(policy['endpoint']).netloc
        seen = set()
        for row in rows[:limit]:
            page_id, title = row['pageid'], row['title']
            if type(page_id) is not int or page_id <= 0 or not isinstance(title, str) or not title:
                raise ValueError('invalid_result')
            if page_id in seen:
                continue
            seen.add(page_id)
            url = f'https://{host}/?curid={page_id}'
            report['results'].append(dict(title=title[:300], url=url,
                snippet=plain(row.get('snippet', '')), attribution=f'{title} — Wikipedia contributors',
                history_url=f'https://{host}/w/index.php?curid={page_id}&action=history',
                license_url=policy['license_url']))
        report['status'] = 'ok' if report['results'] else 'no_results'
    except httpx.TimeoutException:
        report.update(status='timeout', results=[])
    except httpx.HTTPError:
        report.update(status='network_error', results=[])
    except (ValueError, KeyError, TypeError, AttributeError):
        report.update(status='invalid_response', results=[])
    return report


def search(source, query, limit, contact, *, transport=None, registry=REGISTRY):
    return asyncio.run(async_search(source, query, limit, contact, transport=transport, registry=registry))


def configured_contact(explicit, env_file):
    if explicit is not None:
        return explicit
    if 'SEARCH_CONTACT' in os.environ:
        return os.environ['SEARCH_CONTACT']
    values = dotenv_values(env_file, interpolate=False) if env_file.is_file() else {}
    return values.get('SEARCH_CONTACT')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('query', nargs='?')
    parser.add_argument('--source', choices=ENDPOINTS, default='wikipedia-ja')
    parser.add_argument('--contact', help='Operator public contact URL or email sent in User-Agent')
    parser.add_argument('--env-file', type=Path, default=DEFAULT_ENV,
                        help='Contact setting only (default: server/search/.env); use server/search/.env for development')
    parser.add_argument('--limit', type=int, choices=range(1, 11), default=5)
    parser.add_argument('--list-sources', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.list_sources:
        print(REGISTRY.read_text(encoding='utf8'))
        return 0
    if not args.query:
        parser.error('query is required')
    if args.output and args.output.exists():
        parser.error('output must be a new file')
    try:
        result = search(args.source, args.query, args.limit, configured_contact(args.contact, args.env_file))
    except ValueError as exc:
        parser.error(str(exc))
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf8') as stream:
            stream.write(encoded + '\n')
        print(json.dumps(dict(status=result['status'], results=len(result['results']))))
    else:
        print(encoded)
    return 0 if result['status'] in ('ok', 'no_results') else 1


if __name__ == '__main__':
    sys.exit(main())
