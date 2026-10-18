"""The runner must not turn missing checks or fixture failures into success."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
import xml.etree.ElementTree as ET


spec = importlib.util.spec_from_file_location('ciel_regression_runner',
    Path(__file__).resolve().parents[3] / 'scripts' / 'server' / 'run-regression.py')
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def test_fixture_failure_is_reported_even_without_test_start(self):
        class Broken(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                raise RuntimeError('fixture failure')

            def test_never_runs(self):
                pass

        result = runner.Result()
        unittest.defaultTestLoader.loadTestsFromTestCase(Broken).run(result)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual(result.cases[0]['status'], 'error')
        self.assertIn('fixture failure', result.cases[0]['reason'])

    def test_subtest_failure_is_not_reported_as_passed(self):
        class Broken(unittest.TestCase):
            def test_subtests(self):
                with self.subTest('synthetic'):
                    self.fail('regression')

        result = runner.Result()
        unittest.defaultTestLoader.loadTestsFromTestCase(Broken).run(result)
        self.assertEqual(result.cases[0]['status'], 'failed')

    def test_reports_preserve_skips_and_incomplete_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            stage = {'suite': 'unit', 'status': 'incomplete', 'cases': [
                {'id': 'synthetic', 'status': 'skipped', 'reason': 'not configured', 'seconds': 0}]}
            code = runner.reports(Path(directory), [stage])
            self.assertEqual(code, 2)
            report = json.loads(Path(directory, 'report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['status'], 'incomplete')
            self.assertEqual(ET.parse(Path(directory, 'junit.xml')).find('.//skipped').get('message'), 'not configured')

    def test_db_and_api_credentials_are_removed_from_unit_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            def run(*args, **kwargs):
                for key in ('CIEL_DB_URL', 'CIEL_TEST_DB_URL', 'OPENAI_API_KEY', 'LIVEKIT_API_SECRET'):
                    self.assertNotIn(key, kwargs['env'])
                Path(directory, 'unit.json').write_text('{"suite":"unit","status":"passed","cases":[]}', encoding='utf-8')
                return Mock(returncode=0)

            with patch.dict(os.environ, {'CIEL_DB_URL': 'synthetic private URL', 'CIEL_TEST_DB_URL': 'synthetic test URL',
                                         'OPENAI_API_KEY': 'synthetic key', 'LIVEKIT_API_SECRET': 'synthetic secret'}), \
                    patch.object(runner.subprocess, 'run', side_effect=run):
                runner.run_suite('unit', Path(directory))

    def test_temporary_database_is_removed_if_tests_raise(self):
        calls = []

        def docker(*args):
            calls.append(args)
            return '127.0.0.1:12345' if args[0] == 'port' else ''

        with patch.object(runner, 'docker', side_effect=docker), \
                patch.object(runner.subprocess, 'run', return_value=Mock(returncode=0)):
            with self.assertRaisesRegex(RuntimeError, 'synthetic test failure'):
                with runner.temporary_database() as url:
                    self.assertTrue(url.endswith('/ciel_concurrency_test'))
                    raise RuntimeError('synthetic test failure')
        self.assertEqual(calls[-1][:2], ('rm', '--force'))
        self.assertEqual(calls[-1][2], calls[0][calls[0].index('--name') + 1])

    def test_secret_is_redacted_from_error_report(self):
        with patch.dict(os.environ, {'CIEL_TEST_DB_URL': 'synthetic-credential-url'}):
            self.assertNotIn('synthetic-credential-url', runner.redact('error: synthetic-credential-url'))
