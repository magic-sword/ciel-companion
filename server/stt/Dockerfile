FROM python:3.11-slim
WORKDIR /eval
RUN pip install --no-cache-dir vosk==0.3.45
ENV OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 CUDA_VISIBLE_DEVICES=""
COPY vosk_engine.py measure.py ./
ENTRYPOINT ["python", "measure.py"]
