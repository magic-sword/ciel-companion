# ローカル LLM（llama.cpp の llama-server）と、GPU・CPU の形を切り替える係（supervisor.py）。docs/operations/shared-llm-api-ja.md。
# llama.cpp は 2026-09-23 のイメージに固める（Qwen3.5・Gemma 4 に対応。自宅サーバーで測った版）
FROM ghcr.io/ggml-org/llama.cpp@sha256:bfb3264fc2166e01e2b4f9b537e45d7006d87c75021b911f132ef607f5bbced3
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3-venv \
 && python3 -m venv /opt/vision-venv \
 && /opt/vision-venv/bin/pip install --no-cache-dir Pillow==13.0.0 \
 && rm -rf /var/lib/apt/lists/*
COPY supervisor.py gateway.py /opt/local-llm/
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s CMD python3 -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('LOCAL_LLM_PORT','8094')+'/health',timeout=3)"
ENTRYPOINT ["/opt/vision-venv/bin/python", "/opt/local-llm/supervisor.py"]
