# Lightweight harness: no torch, speech models or GPU are needed for scoring/body trials.
FROM python:3.11-slim
WORKDIR /workspace/server
COPY agent/requirements-test.txt agent/requirements.txt ./agent/
RUN pip install --no-cache-dir -r agent/requirements-test.txt
COPY agent/*.py ./agent/
COPY agent/tools/ ./agent/tools/
COPY agent/summaries/ ./agent/summaries/
COPY agent/config/ ./agent/config/
COPY minecraft/src/ ./minecraft/src/
COPY minecraft/package.json minecraft/package-lock.json ./minecraft/
COPY minecraft-pointing/ ./minecraft-pointing/
COPY local-llm/supervisor.py ./local-llm/
COPY compose*.yaml ./
COPY benchmark/*.py benchmark/*.json benchmark/*.js ./benchmark/
ENTRYPOINT ["python", "-m", "benchmark.run"]
