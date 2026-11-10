"""Image resizing and HTTP streaming at the shared model ingress."""
import base64
import importlib.util
import io
import json
from pathlib import Path
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PIL import Image

spec = importlib.util.spec_from_file_location('vision_gateway', Path(__file__).resolve().parents[2] / 'local-llm/gateway.py')
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)

def picture(size=(1024, 512), mode='RGB', color='red', exif=None):
    out = io.BytesIO()
    image = Image.new(mode, size, color)
    options = {'exif': exif} if exif else {}
    image.save(out, format='PNG', **options)
    return 'data:image/png;base64,' + base64.b64encode(out.getvalue()).decode()

def decode(url):
    image = Image.open(io.BytesIO(base64.b64decode(url.split(',', 1)[1])))
    image.load()
    return image

class ResizeTest(unittest.TestCase):
    def test_default_bounds_preserve_aspect_and_do_not_enlarge(self):
        self.assertEqual(decode(gateway.resize_image(picture())).size, (256, 128))
        self.assertEqual(decode(gateway.resize_image(picture((80, 40)))).size, (80, 40))
        self.assertEqual(decode(gateway.resize_image(picture((600, 900)))).size, (171, 256))

    def test_custom_size_is_used(self):
        self.assertEqual(decode(gateway.resize_image(picture(), 512)).size, (512, 256))

    def test_orientation_alpha_and_metadata_are_normalized(self):
        exif = Image.Exif();exif[274] = 6;exif[315] = 'private author'
        image = decode(gateway.resize_image(picture(exif=exif)))
        self.assertEqual(image.size, (128, 256))
        self.assertFalse(image.getexif())
        alpha = decode(gateway.resize_image(picture((100, 100), 'RGBA', (255, 0, 0, 0))))
        self.assertEqual(alpha.getpixel((0, 0)), (255, 255, 255))

    def test_bad_and_remote_images_are_refused(self):
        for url in ['https://example.invalid/private.png', 'file:///etc/passwd', 'data:image/png;base64,!!!!', 'data:image/png;base64,YWJj']:
            with self.subTest(url=url), self.assertRaises(gateway.InvalidImage):
                gateway.resize_image(url)
        with mock.patch.object(gateway, 'MAX_PIXELS', 100):
            with self.assertRaises(gateway.InvalidImage):
                gateway.resize_image(picture((20, 20)))

    def test_all_messages_are_prepared_without_changing_text_or_image_detail(self):
        body = {'model': 'local', 'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': 'hello'}, {'type': 'image_url', 'image_url': {'url': picture(), 'detail': 'low'}}]},
            {'role': 'user', 'content': [{'type': 'image_url', 'image_url': picture((600, 600))}]}]}
        self.assertEqual(gateway.prepare(body, 256), 2)
        self.assertEqual(body['messages'][0]['content'][0]['text'], 'hello')
        self.assertEqual(body['messages'][0]['content'][1]['image_url']['detail'], 'low')
        for message in body['messages']:
            image = decode(message['content'][-1]['image_url']['url'])
            self.assertLessEqual(max(image.size), 256)

class HttpTest(unittest.TestCase):
    def setUp(self):
        self.received = []
        received = self.received
        class Backend(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200);self.send_header('Content-Type', 'application/json');self.end_headers()
                self.wfile.write(b'{"modalities":{"vision":true}}')
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                received.append(body)
                self.send_response(200)
                if body.get('stream'):
                    self.send_header('Content-Type', 'text/event-stream');self.end_headers()
                    self.wfile.write(b'data: {"choices":[]}\n\n');self.wfile.flush()
                    self.wfile.write(b'data: [DONE]\n\n')
                else:
                    self.send_header('Content-Type', 'application/json');self.end_headers();self.wfile.write(b'{"ok":true}')
            def log_message(self, *args):pass
        self.backend = ThreadingHTTPServer(('127.0.0.1', 0), Backend)
        self.server = gateway.create_server('127.0.0.1', 0, self.backend.server_port)
        for server in [self.backend, self.server]:
            thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
            self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def post(self, body):
        request = urllib.request.Request(self.url+'/v1/chat/completions', data=json.dumps(body).encode(), headers={'Content-Type':'application/json'})
        return self.opener.open(request, timeout=5)

    def test_resize_happens_before_backend_and_streaming_survives(self):
        body = {'messages':[{'role':'user','content':[{'type':'image_url','image_url':{'url':picture()}}]}], 'stream':True}
        with self.post(body) as response:
            data = response.read()
            self.assertIn(b'data: [DONE]', data)
            self.assertEqual(response.headers['X-Ciel-Image-Max-Edge'], '256')
            self.assertEqual(response.headers['X-Ciel-Image-Count'], '1')
        forwarded = self.received[0]['messages'][0]['content'][0]['image_url']['url']
        self.assertEqual(decode(forwarded).size, (256, 128))

    def test_text_and_capability_requests_remain_supported(self):
        with self.post({'messages':[{'role':'user','content':'hello'}]}) as response:
            self.assertTrue(json.load(response)['ok'])
        self.assertEqual(self.received[0]['messages'][0]['content'], 'hello')
        with self.opener.open(self.url+'/props',timeout=5) as response:
            self.assertTrue(json.load(response)['modalities']['vision'])

    def test_invalid_image_never_reaches_backend(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post({'messages':[{'role':'user','content':[{'type':'image_url','image_url':{'url':'https://private.invalid'}}]}]})
        self.assertEqual(error.exception.code,400)
        self.assertEqual(self.received,[])

    def test_unavailable_backend_is_reported(self):
        self.backend.shutdown();self.backend.server_close()
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post({'messages':[]})
        self.assertEqual(error.exception.code,503)


class DiscoveryTest(unittest.IsolatedAsyncioTestCase):
    async def test_local_capability_is_read_from_the_configured_api(self):
        import httpx
        import models
        for available in [True, False]:
            requested = []
            def handle(request):
                requested.append(str(request.url))
                return httpx.Response(200,json={'modalities':{'vision':available}})
            client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
            with mock.patch('models.is_local',return_value=True), mock.patch.object(models,'LOCAL_URL','http://127.0.0.1:8094/v1'), mock.patch('httpx.AsyncClient',return_value=client):
                self.assertEqual(await models.vision_available(),available)
            self.assertEqual(requested,['http://127.0.0.1:8094/props'])

    async def test_failed_capability_query_never_falls_back_to_cloud(self):
        import httpx
        import models
        def handle(request):raise httpx.ConnectError('offline',request=request)
        client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        with mock.patch('models.is_local',return_value=True), mock.patch('httpx.AsyncClient',return_value=client):
            self.assertFalse(await models.vision_available())
