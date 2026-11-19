# シエルの会話サーバー（GPU 不要。話者の識別の ECAPA も CPU で動かす）
FROM python:3.11-slim

WORKDIR /app
# 話者の識別（ECAPA）用の PyTorch。GPU は読み上げに使うので、CPU 版（小さい）を入れる
RUN pip install --no-cache-dir torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# ECAPA のモデル（speechbrain/spkrec-ecapa-voxceleb、Apache-2.0）をイメージに入れておき、起動のたびに取りに行かない
ENV HF_HOME=/opt/hf
RUN python -c "from speechbrain.inference.speaker import EncoderClassifier as E; E.from_hparams(source='speechbrain/spkrec-ecapa-voxceleb', revision='0f99f2d0ebe89ac095bcc5903c4dd8f72b367286', savedir='/opt/ecapa')"
# 思い出しの埋め込みモデル（cl-nagoya/ruri-v3-30m、Apache-2.0、約 37M）も版を決めて入れておく
RUN python -c "from huggingface_hub import snapshot_download as d; d('cl-nagoya/ruri-v3-30m', revision='24899e5de370b56d179604a007c0d727bf144504')"
ENV HF_HUB_OFFLINE=1
COPY *.py ./
COPY tools/ ./tools/
COPY summaries/ ./summaries/
COPY config/ ./config/
# プラグインが使うモデルファイル（あれば）を先に取得しておく
RUN python -m livekit.agents download-files || true

CMD ["python", "-m", "livekit.agents", "start", "agent.py"]
