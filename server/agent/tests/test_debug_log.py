import json
import os
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

import debug_log


class DebugLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / 'debug'
        patches = [mock.patch.object(debug_log, 'DIR', self.dir), mock.patch.object(debug_log, '_path', None),
                   mock.patch.dict(os.environ, {'CIEL_DEBUG_LOG': ''})]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def lines(self):
        files = list(self.dir.glob('*.jsonl'))
        self.assertEqual(len(files), 1)
        return [json.loads(line) for line in files[0].read_text(encoding='utf-8').splitlines()]

    def test_off_by_default_writes_nothing(self):
        debug_log.start('ciel-room')
        debug_log.record('item', text='こんにちは')
        self.assertFalse(self.dir.exists() and any(self.dir.glob('*.jsonl')))

    def test_on_file_enables_logging_for_new_conversation(self):
        self.dir.mkdir(parents=True)
        (self.dir / 'ON').touch()
        debug_log.start('ciel-room', voice='irodori')
        debug_log.record('item', role='user', text='こんにちは')
        rows = self.lines()
        self.assertEqual([r['kind'] for r in rows], ['start', 'item'])
        self.assertEqual(rows[0]['voice'], 'irodori')
        self.assertEqual(rows[1]['text'], 'こんにちは')

    def test_environment_variable_enables_logging(self):
        with mock.patch.dict(os.environ, {'CIEL_DEBUG_LOG': '1'}):
            debug_log.start('ciel-room')
        debug_log.record('latency', stage='最初の声', ms=1342)
        self.assertEqual(self.lines()[-1]['ms'], 1342)

    def test_long_values_are_clipped(self):
        with mock.patch.dict(os.environ, {'CIEL_DEBUG_LOG': '1'}):
            debug_log.start('ciel-room')
        debug_log.record('tool', output='あ' * (debug_log.TEXT_LIMIT + 10))
        self.assertTrue(self.lines()[-1]['output'].endswith('（10 字省略）'))

    def test_old_files_are_removed_even_when_off(self):
        self.dir.mkdir(parents=True)
        old, new = self.dir / 'old.jsonl', self.dir / 'new.jsonl'
        old.write_text('{}\n')
        new.write_text('{}\n')
        past = time.time() - (debug_log.DAYS + 1) * 86400
        os.utime(old, (past, past))
        debug_log.start('ciel-room')
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())

    def test_attach_does_nothing_when_off(self):
        session = SimpleNamespace(generate_reply=object(), on=mock.Mock())
        agent = SimpleNamespace(update_instructions=object())
        original = session.generate_reply
        debug_log.attach(session, SimpleNamespace(on=mock.Mock()), agent)
        self.assertIs(session.generate_reply, original)
        session.on.assert_not_called()

    def test_attach_records_reply_requests_and_calls_original(self):
        with mock.patch.dict(os.environ, {'CIEL_DEBUG_LOG': '1'}):
            debug_log.start('ciel-room')
        generate = mock.Mock(return_value='handle')
        session = SimpleNamespace(generate_reply=generate, on=mock.Mock())
        debug_log.attach(session, SimpleNamespace(on=mock.Mock()), SimpleNamespace(update_instructions=mock.AsyncMock()))
        self.assertEqual(session.generate_reply(instructions='[発言者：ハカセ]'), 'handle')
        generate.assert_called_once_with(instructions='[発言者：ハカセ]')
        self.assertEqual(self.lines()[-1]['kind'], 'reply_request')
        self.assertEqual(self.lines()[-1]['instructions'], '[発言者：ハカセ]')


if __name__ == '__main__':
    unittest.main()
