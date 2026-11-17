import importlib.util
import json
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('approved_search', ROOT / 'server/search/approved_search.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ApprovedSearchTests(unittest.TestCase):
    def run_search(self, handler):
        with patch.object(module, 'date') as clock:
            clock.today.return_value = date(2026, 11, 17)
            clock.fromisoformat.side_effect = date.fromisoformat
            return module.search('wikipedia-ja', 'Python', 2, 'https://example.org/contact',
                                 transport=httpx.MockTransport(handler))

    def test_one_api_request_preserves_attribution_without_crawling(self):
        calls = []
        def handler(request):
            calls.append(request)
            self.assertEqual(request.url.host, 'ja.wikipedia.org')
            self.assertEqual(request.url.path, '/w/api.php')
            self.assertEqual(request.url.params['maxlag'], '5')
            return httpx.Response(200, json={'query': {'search': [dict(pageid=123,
                title='Python', snippet='<span>Python</span> &amp; code<script>bad()</script>')]}})
        result = self.run_search(handler)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['results'][0]['snippet'], 'Python & code')
        self.assertIn('history_url', result['results'][0])
        self.assertFalse(result['pages_fetched'])

    def test_redirect_and_rate_limit_do_not_retry(self):
        for status, expected in [(302, 'redirect_refused'), (429, 'rate_limited')]:
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(status, headers={'Location': 'https://unapproved.example/', 'Retry-After': '60'})
            result = self.run_search(handler)
            self.assertEqual(result['status'], expected)
            self.assertEqual(len(calls), 1)
            self.assertEqual(result['results'], [])

    def test_unknown_changed_and_expired_sources_fail_before_network(self):
        with self.assertRaisesRegex(ValueError, 'unapproved_source'):
            module.source_policy('google')
        with tempfile.TemporaryDirectory() as folder:
            registry = Path(folder) / 'sources.json'
            data = json.loads(module.REGISTRY.read_text(encoding='utf8'))
            data['sources']['wikipedia-ja']['endpoint'] = 'http://127.0.0.1/api'
            registry.write_text(json.dumps(data), encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'unapproved_endpoint'):
                module.source_policy('wikipedia-ja', registry, date(2026, 11, 17))
        with self.assertRaisesRegex(ValueError, 'policy_review_required'):
            module.source_policy('wikipedia-ja', today=date(2027, 2, 15))

    def test_errors_and_malformed_data_are_not_success(self):
        for payload, status in [({'error': {'code': 'maxlag'}}, 'api_error'),
                                ({'query': {'search': [{'title': 'broken'}]}}, 'invalid_response'),
                                ({'query': {'search': []}}, 'no_results')]:
            result = self.run_search(lambda request: httpx.Response(200, json=payload))
            self.assertEqual(result['status'], status)
            self.assertEqual(result['results'], [])

    def test_contact_required_before_network(self):
        with patch.object(module, 'source_policy', return_value={}), patch.object(module.httpx, 'AsyncClient') as client:
            with self.assertRaisesRegex(ValueError, 'operator_contact_required'):
                module.search('wikipedia-ja', 'Python', 1, None)
            client.assert_not_called()

    def test_oversized_response_rejected(self):
        result = self.run_search(lambda request: httpx.Response(200, content=b' ' * 1_000_001))
        self.assertEqual(result['status'], 'response_too_large')


if __name__ == '__main__':
    unittest.main()
