#!/usr/bin/env python3
"""Bounded cancellation test against the existing native model; requires idle slots."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import secrets
import threading
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gateway', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--upstream-port', type=int, default=18094)
    parser.add_argument('--rounds', type=int, default=3)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Output must be new')
    def slots():
        with urllib.request.urlopen(f'http://127.0.0.1:{args.upstream_port}/slots', timeout=3) as response:
            return json.load(response)
    if any(s['is_processing'] for s in slots()):
        raise RuntimeError('Shared model is busy; do not contaminate another request')
    spec = importlib.util.spec_from_file_location('measured_gateway', args.gateway)
    gateway = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gateway)
    server = gateway.create_server('127.0.0.1', 0, args.upstream_port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    result = {'gateway_sha256':hashlib.sha256(args.gateway.read_bytes()).hexdigest(),
              'scope':'Disconnect during prefill; same native model, isolated ingress, no voice measurement', 'trials':[]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        for repeat in range(args.rounds):
            if any(s['is_processing'] for s in slots()):
                raise RuntimeError('Shared inference became busy')
            # Different prefixes prevent one trial from warming the next.
            body = json.dumps({'model':'local','messages':[{'role':'user','content':
                secrets.token_hex(16)+': '+('Explain this observation carefully. '*900)}],
                'stream':True,'max_tokens':64,'chat_template_kwargs':{'enable_thinking':False}}).encode()
            client = socket.create_connection(server.server_address, timeout=3)
            client.sendall(f'POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n'.encode()+body)
            deadline = time.monotonic()+5
            while not any(s['is_processing'] for s in slots()):
                if time.monotonic() >= deadline:
                    client.close()
                    raise TimeoutError('Inference did not start')
                time.sleep(.05)
            time.sleep(.2)
            started = time.monotonic()
            client.close()
            deadline = started+40
            while any(s['is_processing'] for s in slots()):
                if time.monotonic() >= deadline:
                    raise TimeoutError('Cancelled inference still occupies a slot after 40 seconds')
                time.sleep(.05)
            result['trials'].append({'repeat':repeat,'release_ms':(time.monotonic()-started)*1000})
            args.output.write_text(json.dumps(result,indent=2))
            print(result['trials'][-1], flush=True)
    except Exception as exc:
        result['error'] = type(exc).__name__
        raise
    finally:
        args.output.write_text(json.dumps(result,indent=2))
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
