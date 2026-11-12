import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
import json
from server.benchmark.within_reply import metrics, reconstruct, stream


class WithinReplyTest(unittest.TestCase):
    def test_loop_severity_survives_truncation(self):
        unit='今日の作業について聞かせてください。どんな家を作りたいですか。'
        small=metrics(unit*3,'length');large=metrics(unit*20,'length')
        self.assertTrue(small['censored']);self.assertFalse(small['natural_stop'])
        self.assertEqual(small['longest_cycles'],3)
        self.assertEqual(large['longest_cycles'],20)
        self.assertGreater(large['duplicate_chars'],small['duplicate_chars'])
        self.assertLess(large['literal_nonduplication_0_5'],small['literal_nonduplication_0_5'])

    def test_empty_failure_is_not_perfect(self):
        value=metrics('',None)
        self.assertIsNone(value['literal_nonduplication_0_5'])
        self.assertTrue(value['censored'])

    def test_normal_and_requested_repeat_have_separate_quality(self):
        self.assertFalse(metrics('今日は散歩に出かけました。道端の花がきれいでした。','stop')['loop_observed'])
        value=metrics('今日はいい天気ですね。'*8,'stop')
        self.assertTrue(value['loop_observed']);self.assertTrue(value['natural_stop'])
        self.assertIsNone(value['quality_0_4'])

    def test_reconstruction_never_includes_target_or_auth_events(self):
        rows=[{'kind':'data','secret':'private'},{'kind':'item','role':'user','text':'hello'},
              {'kind':'thought_opening','text':'thought'},{'kind':'reply_request','instructions':'instruction'},
              {'kind':'speech','id':'target'},{'kind':'item','role':'assistant','text':'future'}]
        h,i,t=reconstruct(rows,'target')
        self.assertEqual(h,[{'role':'user','content':'hello'}]);self.assertEqual(t,'thought')

    def test_timeout_preserves_partial_output_and_events(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def raise_for_status(self):pass
            def iter_lines(self):
                yield 'data: '+json.dumps({'choices':[{'delta':{'content':'今日はいい天気ですね。'*4}}]})
                raise TimeoutError('test deadline')
        class Client(Response):
            def stream(self,*args,**kwargs):return Response()
        with tempfile.TemporaryDirectory() as d, patch('server.benchmark.within_reply.httpx.Client',return_value=Client()):
            path=Path(d)/'events.jsonl'
            row=stream({},'http://localhost/v1',120,path)
            self.assertEqual(row['metrics']['longest_cycles'],4)
            self.assertTrue(row['metrics']['censored'])
            self.assertIn('TimeoutError',row['error'])
            self.assertEqual(len(path.read_text().splitlines()),1)


if __name__=='__main__':unittest.main()
