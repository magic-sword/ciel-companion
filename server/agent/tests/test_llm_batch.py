import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch


class BatchConfigurationTest(unittest.TestCase):
    def test_smaller_microbatch_preserves_context_and_parallelism(self):
        script=Path(__file__).parents[2]/'local-llm/supervisor.py'
        for size in ('128','256','512'):
            with patch.dict(os.environ, {'LOCAL_LLM_UBATCH':size,'LOCAL_LLM_CTX':'32768','LOCAL_LLM_PARALLEL':'2'},clear=True):
                config=runpy.run_path(str(script),run_name='batch_test')
            args=config['COMMON']
            self.assertEqual(args[args.index('--ubatch-size')+1],size)
            self.assertEqual(args[args.index('-c')+1],'65536')
            self.assertEqual(args[args.index('--parallel')+1],'2')

    def test_invalid_batch_fails_before_starting_server(self):
        with patch.dict(os.environ, {'LOCAL_LLM_UBATCH':'0'},clear=True), self.assertRaises(ValueError):
            runpy.run_path(str(Path(__file__).parents[2]/'local-llm/supervisor.py'),run_name='batch_test')
