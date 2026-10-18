#!/usr/bin/env python3
"""Run repeatable offline and isolated PostgreSQL regression suites. Python 3.11+."""
import argparse
import asyncio
import contextlib
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import unittest
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / 'server' / 'agent' / 'tests'
DB_TESTS = {'test_shared_memory_postgres.py'}
DB_IMAGE = 'pgvector/pgvector:0.8.0-pg17'


def redact(text):
    for key, value in os.environ.items():
        if value and any(word in key.upper() for word in ('SECRET', 'PASSWORD', 'TOKEN', 'API_KEY', 'DB_URL')):
            text = text.replace(value, '[redacted]')
    return text


class Result(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.cases = []
        self.case = None

    def outcome(self, test, status, reason):
        if self.case is not None and self.case['id'] == test.id():
            self.case.update(status=status, reason=redact(reason))
        else:
            # setUpClass/setUpModule failures have no startTest/stopTest pair.
            self.cases.append({'id': test.id(), 'status': status, 'reason': redact(reason), 'seconds': 0})

    def startTest(self, test):
        super().startTest(test)
        self.started = time.monotonic()
        self.case = {'id': test.id(), 'status': 'passed', 'reason': ''}

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.outcome(test, 'failed', self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self.outcome(test, 'error', self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.outcome(test, 'skipped', reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.outcome(test, 'skipped', 'expected failure: ' + self._exc_info_to_string(err, test))

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.outcome(test, 'failed', 'unexpected success; update the expected-failure marker')

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.outcome(test, 'failed', self._exc_info_to_string(err, subtest))

    def stopTest(self, test):
        self.case['seconds'] = round(time.monotonic() - self.started, 4)
        self.cases.append(self.case)
        self.case = None
        super().stopTest(test)


def worker(suite, output):
    if sys.platform == 'win32':
        # psycopg's async connections require a selector loop on Windows (Python 3.11/3.12).
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.path.insert(0, str(ROOT / 'server' / 'agent'))
    tests = unittest.TestSuite()
    for path in sorted(TESTS.glob('test_*.py')):
        if (path.name in DB_TESTS) == (suite == 'db'):
            tests.addTests(unittest.defaultTestLoader.discover(str(TESTS), pattern=path.name))
    result = Result()
    # Capture warnings as well as test output; do not echo private environment-dependent exceptions.
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        tests.run(result)
    status = ('failed' if not result.wasSuccessful() or not result.testsRun else
              'incomplete' if result.skipped or result.expectedFailures else 'passed')
    Path(output).write_text(json.dumps({'suite': suite, 'status': status, 'cases': result.cases,
                                       'diagnostics': redact(stream.getvalue())}, ensure_ascii=False, indent=2), encoding='utf-8')


def docker(*args):
    result = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=120)
    if result.returncode:
        # Docker may echo environment arguments containing a temporary password; keep this diagnostic bounded.
        raise RuntimeError('Docker command failed: ' + args[0] + '. Check that Docker is running and the image is available.')
    return result.stdout.strip()


@contextlib.contextmanager
def temporary_database():
    name = 'ciel-regression-' + uuid.uuid4().hex[:12]
    password = secrets.token_hex(24)
    created = False
    try:
        docker('run', '--detach', '--rm', '--name', name, '--memory', '256m', '--cpus', '1',
               '--publish', '127.0.0.1::5432', '-e', 'POSTGRES_DB=ciel_concurrency_test',
               '-e', 'POSTGRES_PASSWORD=' + password, DB_IMAGE)
        created = True
        deadline = time.monotonic() + 45
        while True:
            ready = subprocess.run(['docker', 'exec', name, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres',
                                    '-d', 'ciel_concurrency_test'],
                                   capture_output=True, timeout=10)
            if ready.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('Temporary PostgreSQL did not become ready within 45 seconds')
            time.sleep(.5)
        port = docker('port', name, '5432/tcp').splitlines()[0].rsplit(':', 1)[1]
        yield f'postgresql://postgres:{password}@127.0.0.1:{port}/ciel_concurrency_test'
    finally:
        try:
            docker('rm', '--force', name)  # Only the container created by this invocation; no host volumes.
        except Exception:
            if created:
                raise


def run_suite(suite, directory, db_url=None, timeout=300):
    environment = dict(os.environ)
    for key in ('CIEL_DB_URL', 'CIEL_TEST_DB_URL', 'OPENAI_API_KEY', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET',
                'CIEL_MINUTES_DISCORD_WEBHOOK'):
        environment.pop(key, None)
    if db_url:
        environment['CIEL_TEST_DB_URL'] = db_url
    environment.update(PYTHONUTF8='1', HF_HUB_OFFLINE='1')
    output = directory / (suite + '.json')
    try:
        completed = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker', suite,
                                    '--worker-output', str(output)], cwd=ROOT / 'server' / 'agent',
                                   env=environment, capture_output=True, timeout=timeout)
        if completed.returncode or not output.is_file():
            raise RuntimeError('Test process failed before producing a report; check Python and test dependencies')
        return json.loads(output.read_text(encoding='utf-8'))
    except subprocess.TimeoutExpired:
        return {'suite': suite, 'status': 'error', 'reason': f'Test process exceeded {timeout} seconds', 'cases': []}


def reports(directory, stages):
    failed = any(s['status'] in ('failed', 'error') for s in stages)
    incomplete = any(s['status'] == 'incomplete' for s in stages)
    revision, dirty = None, None
    try:
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, timeout=10)
        state = subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT, capture_output=True, text=True, timeout=10)
        revision = head.stdout.strip() if head.returncode == 0 else None
        dirty = bool(state.stdout.strip()) if state.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        pass
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'python': sys.version.split()[0],
              'git_revision': revision, 'working_tree_dirty': dirty,
              'status': 'failed' if failed else 'incomplete' if incomplete else 'passed', 'stages': stages}
    (directory / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    root = ET.Element('testsuites')
    for stage in stages:
        cases = stage['cases'] or [{'id': stage['suite'], 'status': stage['status'], 'reason': stage.get('reason', '')}]
        suite = ET.SubElement(root, 'testsuite', name=stage['suite'], tests=str(len(cases)),
                              failures=str(sum(c['status'] in ('failed', 'error') for c in cases)),
                              skipped=str(sum(c['status'] in ('skipped', 'incomplete') for c in cases)))
        for case in cases:
            node = ET.SubElement(suite, 'testcase', name=case['id'], time=str(case.get('seconds', 0)))
            if case['status'] in ('failed', 'error', 'skipped', 'incomplete'):
                tag = 'skipped' if case['status'] in ('skipped', 'incomplete') else 'failure'
                ET.SubElement(node, tag, message=case.get('reason', '')).text = case.get('reason', '')
    ET.ElementTree(root).write(directory / 'junit.xml', encoding='utf-8', xml_declaration=True)
    return 1 if failed else 2 if incomplete else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=('unit', 'db', 'all'), default='unit')
    parser.add_argument('--db-mode', choices=('docker', 'external'), default='docker')
    parser.add_argument('--output', type=Path, help='New result directory (default: .local/regression/<UTC timestamp-ID>)')
    parser.add_argument('--timeout', type=int, default=300, help='Timeout per test suite in seconds')
    parser.add_argument('--worker', choices=('unit', 'db'), help=argparse.SUPPRESS)
    parser.add_argument('--worker-output', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.worker_output)
        return 0
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    directory = (args.output or ROOT / '.local' / 'regression' /
                 (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6])).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    stages = []
    for suite in ('unit', 'db'):
        if args.suite not in (suite, 'all'):
            stages.append({'suite': suite, 'status': 'skipped', 'reason': 'Not selected by --suite', 'cases': []})
            continue
        try:
            if suite == 'unit':
                result = run_suite(suite, directory, timeout=args.timeout)
            elif args.db_mode == 'docker':
                with temporary_database() as url:
                    result = run_suite(suite, directory, url, args.timeout)
            else:
                url = os.environ.get('CIEL_TEST_DB_URL')
                if not url:
                    raise RuntimeError('External DB requested but CIEL_TEST_DB_URL is not set; DB tests were not run')
                result = run_suite(suite, directory, url, args.timeout)
        except Exception as error:
            result = {'suite': suite, 'status': 'error', 'reason': redact(str(error)), 'cases': []}
        stages.append(result)
    code = reports(directory, stages)
    for stage in stages:
        counts = {status: sum(c['status'] == status for c in stage['cases'])
                  for status in ('passed', 'failed', 'error', 'skipped')}
        print(f"{stage['suite']}: {stage['status']} {counts} {stage.get('reason', '')}")
        for case in stage['cases']:
            if case['status'] in ('failed', 'error', 'skipped'):
                print(' ', case['status'], case['id'])
    print('Reports:', directory)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
