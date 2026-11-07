# ローカル LLM（llama.cpp の llama-server）と、GPU・CPU の形を切り替える係（supervisor.py）。docs/local-llm-ja.md。
# llama.cpp は 2026-09-23 のイメージに固める（Qwen3.5・Gemma 4 に対応。自宅サーバーで測った版）
FROM ghcr.io/ggml-org/llama.cpp@sha256:bfb3264fc2166e01e2b4f9b537e45d7006d87c75021b911f132ef607f5bbced3
COPY supervisor.py /opt/local-llm/supervisor.py
ENTRYPOINT ["python3", "/opt/local-llm/supervisor.py"]
