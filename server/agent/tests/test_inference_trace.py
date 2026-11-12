import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, AsyncMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
import inference_trace as trace
import debug_log


class TraceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'session.jsonl'
        self.env=patch.dict(os.environ,{'CIEL_AGENT_NAME':'ciel-dev','CIEL_INFERENCE_TRACE':'1','OPENAI_API_KEY':'secret-value-123'})
        self.env.start();self.addCleanup(self.env.stop)
        self.old=patch.object(debug_log,'_path',self.path);self.old.start();self.addCleanup(self.old.stop)
        trace._disabled.clear()

    def rows(self):
        return [json.loads(l) for l in (self.path.parent/'traces'/self.path.name).read_text().splitlines()]

    def test_no_production_and_no_auth_leak(self):
        with patch.dict(os.environ,{'CIEL_AGENT_NAME':'ciel'}):
            self.assertFalse(trace.write('test',text='private'))
        trace.write('test',payload={'messages':[{'content':'secret-value-123'}],
                    'arguments':'{"deviceSecret":"private"}','authorization':'Bearer xyz'})
        raw=json.dumps(self.rows())
        self.assertNotIn('secret-value-123',raw);self.assertNotIn('private',raw);self.assertNotIn('xyz',raw)

    def test_long_input_is_not_silently_clipped_and_quota_marks_loss(self):
        trace.write('request',text='a'*9000)
        self.assertEqual(len(self.rows()[0]['text']),9000)
        with patch.object(trace,'EVENT_LIMIT',100):self.assertFalse(trace.write('huge',text='a'*200))
        self.assertEqual(self.rows()[-1]['kind'],'trace_incomplete')
        self.assertFalse(trace.write('later',text='lost'))

    async def test_http_payload_and_stream_are_unchanged_and_correlated(self):
        chunks=[b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n',b'data: [DONE]\n\n']
        class Bytes(httpx.AsyncByteStream):
            async def __aiter__(self):
                for c in chunks:yield c
        payload={'model':'local','messages':[{'role':'user','content':'hello'}],
                 'tools':[{'type':'function','function':{'name':'test','parameters':{'type':'object'}}}], 'temperature':0.7}
        def handler(request):
            self.assertEqual(json.loads(request.content),payload)
            return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Bytes())
        transport=trace.Transport(httpx.MockTransport(handler))
        transport.metadata=AsyncMock(return_value={'mode':{'generation':'abc'}})
        token=trace.correlation.set({'request_id':'r','speech_id':'s'})
        try:
            async with httpx.AsyncClient(transport=transport) as client:
                async with client.stream('POST','http://local/chat/completions',json=payload) as r:
                    self.assertEqual(b''.join([c async for c in r.aiter_bytes()]),b''.join(chunks))
        finally:trace.correlation.reset(token)
        rows=self.rows();self.assertEqual(rows[0]['payload'],payload)
        self.assertTrue(rows[-1]['done_marker']);self.assertEqual(rows[0]['speech_id'],'s')
        self.assertEqual(trace.export_request(self.path.parent/'traces'/self.path.name,rows[0]['http_id']),payload)

    async def test_interruption_preserves_partial_output(self):
        class Broken(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
                raise httpx.ReadError('broken')
        with self.assertRaises(httpx.ReadError):
            async for _ in trace.Stream(Broken(),{'request_id':'r'}):pass
        rows=self.rows();self.assertEqual(rows[0]['event']['choices'][0]['delta']['content'],'partial')
        self.assertFalse(rows[-1]['done_marker'])

    def test_expired_traces_are_removed(self):
        trace.write('test',text='old')
        p=self.path.parent/'traces'/self.path.name;os.utime(p,(1,1))
        with patch.object(debug_log,'DIR',self.path.parent):debug_log.cleanup()
        self.assertFalse(p.exists())


if __name__=='__main__':unittest.main()
