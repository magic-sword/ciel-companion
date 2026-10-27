# 歌を聴くサービス（server.py）。Audiobox Aesthetics・MERT・CREPE を自宅の GPU で動かす。歌声は外へ送らない
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# モデル（版は server.py で固定）をイメージに入れておき、起動のたびに取りに行かない。
# MERT は同梱のコードを読み込む（trust_remote_code）。版を固定しているので、上流が書き換えても変わらない
ENV HF_HOME=/opt/hf
COPY server.py analysis.py ./
RUN SING_DEVICE=cpu python -c "import server; server.Models()"
ENV HF_HUB_OFFLINE=1
CMD ["python", "server.py"]
