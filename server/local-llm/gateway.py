"""Loopback OpenAI API ingress: bound and resize inline images before inference."""
import base64
import binascii
import io
import json
import collections
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BODY = 16 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 24_000_000
HOP_HEADERS = {'connection', 'transfer-encoding', 'keep-alive', 'te', 'trailer',
               'upgrade', 'proxy-authorization', 'proxy-authenticate', 'host', 'content-length'}

class Admission:
    """Bounded foreground FIFO; at most one background request uses inference."""
    def __init__(self, parallel=2, capacity=64):
        self.parallel, self.capacity = parallel, capacity
        self.condition = threading.Condition()
        self.waiting = collections.deque()
        self.active = self.background = 0

    def acquire(self, work, timeout=30):
        if work not in ('foreground', 'background'):
            raise ValueError('Invalid X-Ciel-Work-Class')
        start = time.monotonic()
        ticket = object()
        with self.condition:
            if len(self.waiting) + self.active >= self.capacity:
                raise TimeoutError('Inference admission capacity exceeded')
            self.waiting.append((ticket, work))
            try:
                while True:
                    foreground = [t for t, kind in self.waiting if kind == 'foreground']
                    first = foreground[0] if foreground else self.waiting[0][0]
                    background_limit = 1
                    if (ticket is first and self.active < self.parallel and
                            (work == 'foreground' or self.background < background_limit)):
                        self.active += 1
                        self.background += work == 'background'
                        return time.monotonic() - start
                    remaining = timeout - (time.monotonic() - start)
                    if remaining <= 0:
                        raise TimeoutError('Inference admission expired')
                    self.condition.wait(remaining)
            finally:
                self.waiting.remove((ticket, work))
                self.condition.notify_all()

    def release(self, work):
        with self.condition:
            self.active -= 1
            self.background -= work == 'background'
            self.condition.notify_all()


class InvalidImage(ValueError):
    pass

def resize_image(url, max_edge=256):
    if not isinstance(url, str) or not url.startswith(('data:image/jpeg;base64,', 'data:image/png;base64,', 'data:image/webp;base64,')):
        raise InvalidImage('Images must be inline JPEG, PNG or WebP data URLs')
    encoded = url.split(',', 1)[1]
    if len(encoded) > (MAX_IMAGE_BYTES + 2) // 3 * 4:
        raise InvalidImage('Image exceeds byte limit')
    try:
        data = base64.b64decode(encoded, validate=True)
        if len(data) > MAX_IMAGE_BYTES:
            raise InvalidImage('Image exceeds byte limit')
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in ('JPEG', 'PNG', 'WEBP'):
                raise InvalidImage('Unsupported image format')
            if source.width * source.height > MAX_PIXELS:
                raise InvalidImage('Image exceeds pixel limit')
            oriented = ImageOps.exif_transpose(source)
            oriented.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
            rgba = oriented.convert('RGBA')
            image = Image.new('RGB', rgba.size, 'white')
            image.paste(rgba, mask=rgba.getchannel('A'))
            image.info.clear()
            out = io.BytesIO()
            image.save(out, format='PNG')
    except (UnidentifiedImageError, OSError, binascii.Error, Image.DecompressionBombError) as error:
        raise InvalidImage('Invalid image data') from error
    return 'data:image/png;base64,' + base64.b64encode(out.getvalue()).decode('ascii')

def prepare(body, max_edge):
    if not isinstance(body, dict) or not isinstance(body.get('messages', []), list):
        raise ValueError('Invalid chat request')
    count = 0
    for message in body.get('messages', []):
        if not isinstance(message, dict):
            raise ValueError('Invalid message')
        content = message.get('content')
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get('type') != 'image_url':
                continue
            value = part.get('image_url')
            url = value.get('url') if isinstance(value, dict) else value
            normalized = resize_image(url, max_edge)
            part['image_url'] = {**value, 'url': normalized} if isinstance(value, dict) else {'url': normalized}
            count += 1
    return count

def create_server(host, port, upstream_port, *, max_edge=256, parallel=2):
    if not 32 <= max_edge <= 4096:
        raise ValueError('LOCAL_LLM_IMAGE_MAX_EDGE must be between 32 and 4096')
    upstream = f'http://127.0.0.1:{upstream_port}'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    admission = Admission(parallel)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def setup(self):
            super().setup()
            self.connection.settimeout(180)

        def error(self, status, message, code='invalid_request'):
            data = json.dumps({'error': {'type': 'invalid_request_error', 'code': code, 'message': message}}).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            self.wfile.write(data)

        def forward(self):
            response_started = False
            admitted = False
            work = self.headers.get('X-Ciel-Work-Class', 'foreground')
            queued = 0.0
            try:
                path = urllib.parse.urlsplit(self.path)
                if path.scheme or path.netloc or not self.path.startswith('/'):
                    return self.error(400, 'Invalid API path')
                if self.headers.get('Transfer-Encoding'):
                    return self.error(400, 'A Content-Length header is required')
                if self.headers.get('Content-Encoding', 'identity') != 'identity':
                    return self.error(415, 'Compressed request bodies are not supported')
                size = int(self.headers.get('Content-Length', '0'))
                if size < 0 or size > MAX_BODY:
                    return self.error(413, 'Request exceeds byte limit')
                data = self.rfile.read(size) if size else None
                images = 0
                if self.command == 'POST' and path.path.rstrip('/') == '/v1/chat/completions':
                    body = json.loads(data or b'{}')
                    images = prepare(body, max_edge)
                    data = json.dumps(body, ensure_ascii=False).encode('utf-8')
                    queued = admission.acquire(work)
                    admitted = True
                headers = {key: value for key, value in self.headers.items() if key.lower() not in HOP_HEADERS}
                if data is not None:
                    headers['Content-Length'] = str(len(data))
                request = urllib.request.Request(upstream + self.path, data=data, headers=headers, method=self.command)
                try:
                    response = opener.open(request, timeout=180)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    self.send_response(response.status)
                    for key, value in response.headers.items():
                        if key.lower() not in HOP_HEADERS:
                            self.send_header(key, value)
                    self.send_header('X-Ciel-Image-Max-Edge', str(max_edge))
                    self.send_header('X-Ciel-Image-Count', str(images))
                    self.send_header('X-Ciel-Admission-Ms', str(round(queued * 1000, 2)))
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    response_started = True
                    self.close_connection = True
                    while True:
                        chunk = response.read1(16384)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()
            except InvalidImage as error:
                if not response_started:
                    self.error(400, str(error), 'invalid_image')
            except TimeoutError:
                if not response_started:
                    self.error(503 if admitted else 429,
                               'Inference timed out' if admitted else 'Inference admission expired',
                               'inference_unavailable' if admitted else 'inference_busy')
            except (ValueError, UnicodeError):
                if not response_started:
                    self.error(400, 'Invalid JSON request')
            except (BrokenPipeError, ConnectionResetError):
                pass  # Closing the upstream connection also cancels generation.
            except (OSError, urllib.error.URLError):
                if not response_started:
                    self.error(503, 'Local inference is temporarily unavailable', 'inference_unavailable')
            finally:
                if admitted:
                    admission.release(work)

        do_GET = do_POST = do_DELETE = do_OPTIONS = forward

        def log_message(self, *args):
            pass  # Never log prompts, image data, credentials or image URLs.

    return ThreadingHTTPServer((host, port), Handler)
