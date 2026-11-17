#!/usr/bin/env python3
"""Run the fixture experiment through an owned SSH tunnel to the shared Qwen API."""
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('benchmark_home', Path(__file__).with_name('benchmark-home.py'))
home = importlib.util.module_from_spec(spec)
spec.loader.exec_module(home)

STATUS = "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8095/mode',timeout=5).read().decode())"


def status():
    result = subprocess.run(home.ssh_args() + ['python3 -'], input=STATUS, text=True,
                            capture_output=True, timeout=25, check=True)
    return json.loads(result.stdout)


def main(script='server/benchmark/continuation.py'):
    args = sys.argv[1:]
    if '--output' not in args or '--base-url' in args:
        raise SystemExit('Pass --output and benchmark options; base URL is owned by this wrapper')
    output = Path(args[args.index('--output')+1])
    if output.exists():
        raise SystemExit('Output already exists')
    before = status()
    if before.get('mode') != 'gpu' or not before.get('ready'):
        raise SystemExit('Shared API is not ready in GPU mode; no mode change was attempted')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    ssh = home.ssh_args()
    tunnel = subprocess.Popen(ssh[:-1] + ['-N', '-o', 'ExitOnForwardFailure=yes', '-L',
        f'127.0.0.1:{port}:127.0.0.1:8094', ssh[-1]], stdout=subprocess.DEVNULL,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        for _ in range(40):
            if tunnel.poll() is not None:
                raise RuntimeError('SSH tunnel exited')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(.25)
        else:
            raise TimeoutError('Tunnel health check failed')
        result = subprocess.run([sys.executable, str(ROOT/script),
            '--base-url', f'http://127.0.0.1:{port}', *args], cwd=ROOT)
        return result.returncode
    finally:
        tunnel.terminate()
        try:
            tunnel.wait(timeout=5)
        except subprocess.TimeoutExpired:
            tunnel.kill()
            tunnel.wait()
        if output.exists():
            report = json.loads(output.read_text(encoding='utf-8'))
            report['mode_before'] = before
            try:
                report['mode_after'] = status()
            except Exception as error:
                report['mode_after'] = {'unavailable': type(error).__name__}
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    raise SystemExit(main())
