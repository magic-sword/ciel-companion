# Irodori-TTS（コード MIT、モデル Aratako/Irodori-TTS-v4.1-Small も MIT）で、シエルの声を直接読み上げるサービス（server.py）。速さの測定は bench_tts.py。
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.8.15
# 版を固定（2026-09-12 のコミット。ユーザーのボイスサンプル作成に使ったものと同じ）
ARG IRODORI_COMMIT=89f9d8fbd4d51ea019867ee1197725ede1df13c5
RUN git clone https://github.com/Aratako/Irodori-TTS.git /opt/irodori && git -C /opt/irodori checkout ${IRODORI_COMMIT}
WORKDIR /opt/irodori
RUN uv sync --extra cu128 --frozen
COPY *.py /app/
ENV HF_HOME=/data/hf
CMD ["uv", "run", "--no-sync", "python", "/app/server.py"]
