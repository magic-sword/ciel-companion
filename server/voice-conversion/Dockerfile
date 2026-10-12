# 声質変換サービス（Seed-VC、GPU）。Seed-VC は GPL-3.0 なので、このフォルダも GPL-3.0（LICENSE）。
FROM pytorch/pytorch:2.4.0-cuda12.4-cudnn9-runtime

RUN apt-get update && apt-get install -y --no-install-recommends git ffmpeg && rm -rf /var/lib/apt/lists/*
# Seed-VC は版を固定して取得する（2025-04-20 のコミット）
ARG SEED_VC_COMMIT=51383efd921027683c89e5348211d93ff12ac2a8
RUN git clone https://github.com/Plachtaa/seed-vc.git /opt/seed-vc && git -C /opt/seed-vc checkout ${SEED_VC_COMMIT}
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app
COPY *.py ./
ENV SEED_VC_DIR=/opt/seed-vc HF_HOME=/data/hf
CMD ["python", "server.py"]
