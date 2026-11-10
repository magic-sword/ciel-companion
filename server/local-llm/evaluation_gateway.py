"""Isolated admission/control ingress forwarding to the unchanged shared API.

Generation identifies this evaluation ingress, never the upstream native process.
"""
import json
import threading
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from gateway import create_server


class Mode(BaseHTTPRequestHandler):
    epoch = uuid.uuid4().hex
    def do_GET(self):
        if self.path != '/mode':
            self.send_error(404)
            return
        try:
            with urllib.request.urlopen('http://127.0.0.1:8095/mode', timeout=3) as response:
                data = json.load(response)
            data.update(generation=self.epoch, generation_scope='evaluation_ingress')
            content = json.dumps(data).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception:
            self.send_error(503)
    def log_message(self,*args):
        pass


if __name__=='__main__':
    control = ThreadingHTTPServer(('127.0.0.1',8096),Mode)
    threading.Thread(target=control.serve_forever,daemon=True).start()
    create_server('127.0.0.1',8097,8094,parallel=2).serve_forever()
