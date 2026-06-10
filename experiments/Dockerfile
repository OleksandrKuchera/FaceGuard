FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake \
    libopenblas-dev liblapack-dev \
    libx11-dev libgtk-3-dev \
    libpng16-16 libjpeg62-turbo libwebp7 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY exp_01_distances.py .
COPY exp_02_metrics.py .
COPY exp_03_encryption.py .
COPY exp_04_pipeline.py .

ENTRYPOINT ["bash", "-c"]
