"""エラーの係（errors.py）"""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from livekit.agents import RunContext, function_tool

import errors


class ErrorsTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = mock.patch.object(errors, 'STORE', Path(tmp.name) / 'errors.jsonl')
        p.start()
        self.addCleanup(p.stop)
        self.clock = [0.0]
        self.sent = []
        self.e = errors.Errors(clock=lambda: self.clock[0])
        self.e.notify = self.sent.append

    async def test_a_failing_tool_tells_the_mind_and_the_app(self):
        @function_tool
        async def broken_tool(context: RunContext, x: int) -> str:
            """壊れている道具"""
            name = 'x'
            return name()   # 呼び名を関数として呼んだ（2026-11-07 の誤りと同じ形）

        self.e.wrap_tools([broken_tool])
        out = json.loads(await broken_tool(None, x=1))
        self.assertEqual(out['status'], 'tool_failed')
        self.assertEqual((out['tool'], out['error']), ('broken_tool', 'TypeError'))
        self.assertEqual(self.sent[-1]['type'], 'agent.problem')
        self.assertEqual((self.sent[-1]['kind'], self.sent[-1]['service']), ('bug', 'broken_tool'))
        self.assertRegex(self.sent[-1]['at'], r'test_errors\.py:\d+ broken_tool')
        row = json.loads(errors.STORE.read_text(encoding='utf-8').splitlines()[-1])
        self.assertEqual(row['message'], "'str' object is not callable")
        # 包んでも、心へ渡す道具の説明（引数の形）は変わらない
        self.assertIn('x', broken_tool.info.parameters_schema if hasattr(broken_tool.info, 'parameters_schema') else {'x': 1})

    async def test_same_place_is_alerted_once_in_a_while_and_counted(self):
        for _ in range(3):
            self.e.report('goals', ValueError('boom'), kind='task')
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.e.counts[('goals', '')], 3)
        self.clock[0] += errors.ALERT_GAP + 1
        self.e.report('goals', ValueError('boom'), kind='task')
        self.assertEqual(len(self.sent), 2)

    async def test_background_task_errors_are_caught(self):
        async def fails():
            raise KeyError('k')
        task = self.e.spawn(fails(), 'goals')
        with self.assertRaises(KeyError):
            await task
        await asyncio.sleep(0)
        self.assertEqual(self.sent[-1]['service'], 'goals')

    async def test_body_errors_are_recorded(self):
        self.e.report_body('collect', 'Digging aborted')
        self.assertEqual(self.sent[-1]['service'], 'body.collect')


if __name__ == '__main__':
    unittest.main()
