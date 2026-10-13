# シエルの会話サーバー（フェーズ1：GPU 不要）
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
COPY config/ ./config/
# プラグインが使うモデルファイル（あれば）を先に取得しておく
RUN python -m livekit.agents download-files || true

CMD ["python", "-m", "livekit.agents", "start", "agent.py"]
