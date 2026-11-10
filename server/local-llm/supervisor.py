"""ローカル LLM（llama.cpp の llama-server）を動かし、GPU を使う形と CPU だけの形を切り替える係。docs/operations/local-runtime-ja.md。

- llama-server は OpenAI と同じ形の窓口（LLM_PORT、既定 8094。/v1/chat/completions）。会話サーバーの裏の役目（内なる考え・
  まとめ・メモ・関係・育つ好み）が使う（server/agent/models.py の CIEL_LOCAL_ROLES）。
- gpu の形：MoE の専門家は CPU、残りは GPU（-ngl 99 --n-cpu-moe 99）。内なる考え 1 回 13〜25 秒。GPU を約 2.6 GB 使う。
- cpu の形：GPU を見せずに動かす（CUDA_VISIBLE_DEVICES を空）。1 回 50 秒ほど。歌を聴く係（server/singing）が分析のモデル
  （約 2 GB）を GPU に載せるあいだは、こちらにする（声と LLM と分析が同じ 12 GB の GPU に入らない。2026-11-07 に測った）。
- 切り替えの窓口（CONTROL_PORT、既定 8095）：GET /mode → {"mode", "ready"}、POST /mode {"mode": "cpu"|"gpu"} → 切り替えて、
  動き出すまで待って返す。切り替えのあいだ（読み直しに 10〜30 秒）は LLM が答えないので、呼ぶ側は失敗を飛ばす。
- どちらの窓口も 127.0.0.1 だけで待ち受ける（host のネットワークで動くので、全部のアドレスで開くと外から見える）。
- llama-server が落ちたら、同じ形で起こし直す。
"""
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger('local-llm')

MODEL = os.environ.get('LOCAL_LLM_MODEL', '/models/Qwen3.5-35B-A3B-Q4_K_M.gguf')
HOST = os.environ.get('LOCAL_LLM_HOST', '127.0.0.1')
LLM_PORT = int(os.environ.get('LOCAL_LLM_PORT', '8094'))
INFERENCE_PORT = int(os.environ.get('LOCAL_LLM_INFERENCE_PORT', '18094'))
MMPROJ = os.environ.get('LOCAL_LLM_MMPROJ', '').strip()
IMAGE_MAX_EDGE = int(os.environ.get('LOCAL_LLM_IMAGE_MAX_EDGE', '256'))
CONTROL_PORT = int(os.environ.get('LOCAL_LLM_CONTROL_PORT', '8095'))
CTX = os.environ.get('LOCAL_LLM_CTX', '32768')
PARALLEL = int(os.environ.get('LOCAL_LLM_PARALLEL', '2'))
# With explicit --parallel, llama.cpp divides the total context among slots.
# LOCAL_LLM_CTX describes capacity per request, not the sum across clients.
COMMON = ['-m', MODEL, '--host', HOST, '--port', str(INFERENCE_PORT), '-c', str(int(CTX)*PARALLEL), '-t', '8', '-tb', '16', '--jinja',
          '--alias', os.environ.get('LOCAL_LLM_ALIAS', 'local')]
COMMON += ['--parallel', str(PARALLEL)]
if MMPROJ:
    COMMON += ['--mmproj', MMPROJ, '--no-mmproj-offload', '--image-max-tokens', '1024']
ARGS = {'gpu': ['-ngl', os.environ.get('LOCAL_LLM_GPU_LAYERS', '99'),
                '--n-cpu-moe', os.environ.get('LOCAL_LLM_CPU_MOE_LAYERS', '99')],
        'cpu': ['-ngl', '0']}
READY_TIMEOUT = 180.0

_lock = threading.Lock()
_proc: subprocess.Popen | None = None
_mode = os.environ.get('LOCAL_LLM_MODE', 'gpu')
_stopping = False
_generation = None


def _healthy() -> bool:
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{INFERENCE_PORT}/health', timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _start(mode: str) -> None:
    global _proc, _generation
    env = dict(os.environ)
    if mode == 'cpu':
        env['CUDA_VISIBLE_DEVICES'] = ''   # GPU を見せない（読み込みの手伝いも含めて、GPU のメモリーを使わない）
    _proc = subprocess.Popen(['/app/llama-server', *COMMON, *ARGS[mode]], env=env)
    _generation = uuid.uuid4().hex
    log.info('llama-server を %s の形で起こした（pid %d）', mode, _proc.pid)


def _stop() -> None:
    global _proc
    if _proc is None:
        return
    _proc.send_signal(signal.SIGTERM)
    try:
        _proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        _proc.kill()
        _proc.wait()
    _proc = None


def _wait_ready() -> bool:
    end = time.monotonic() + READY_TIMEOUT
    while time.monotonic() < end:
        if _healthy():
            return True
        if _proc is not None and _proc.poll() is not None:
            return False
        time.sleep(1)
    return False


def switch(mode: str) -> dict:
    global _mode
    with _lock:
        if mode == _mode and _proc is not None and _proc.poll() is None:
            return {'mode': _mode, 'ready': _healthy()}
        _stop()
        _mode = mode
        _start(mode)
        ready = _wait_ready()
        log.info('%s の形に切り替えた（動き出した：%s）', mode, ready)
        return {'mode': _mode, 'ready': ready}


def watch() -> None:
    """llama-server が落ちたら、同じ形で起こし直す"""
    while not _stopping:
        time.sleep(5)
        with _lock:
            if _proc is not None and _proc.poll() is not None and not _stopping:
                log.warning('llama-server が止まった（%s）。起こし直す', _proc.returncode)
                _start(_mode)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path != '/mode':
            return self._send(404, {'error': 'not_found'})
        self._send(200, {'mode': _mode, 'ready': _healthy(), 'model': os.path.basename(MODEL),
                         'context': int(CTX), 'parallel': PARALLEL, 'generation': _generation,
                         'generation_scope': 'inference_process'})

    def do_POST(self):
        if self.path != '/mode':
            return self._send(404, {'error': 'not_found'})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0') or 0)) or b'{}')
        except ValueError:
            return self._send(400, {'error': 'bad_json'})
        mode = body.get('mode')
        if mode not in ARGS:
            return self._send(400, {'error': 'bad_mode'})
        self._send(200, switch(mode))

    def log_message(self, *args):
        pass


def main() -> None:
    global _stopping
    from gateway import create_server
    if MMPROJ and not Path(MMPROJ).is_file():
        raise FileNotFoundError('Configured LOCAL_LLM_MMPROJ does not exist')
    gateway = create_server(HOST, LLM_PORT, INFERENCE_PORT, max_edge=IMAGE_MAX_EDGE, parallel=PARALLEL)
    _start(_mode)
    threading.Thread(target=gateway.serve_forever, daemon=True).start()
    threading.Thread(target=watch, daemon=True).start()

    def bye(*_):
        global _stopping
        _stopping = True
        gateway.shutdown()
        gateway.server_close()
        _stop()
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, bye)
    log.info('切り替えの窓口 http://%s:%d/mode', HOST, CONTROL_PORT)
    ThreadingHTTPServer((HOST, CONTROL_PORT), Handler).serve_forever()


if __name__ == '__main__':
    main()
