# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
    REDACT_OFFLINE=1

# Install essential system libraries required by OpenCV headless and Paddle
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency manifest
COPY requirements.txt .

# 1. Upgrade pip
# 2. Install CPU-only PyTorch wheel (lean ~190MB, avoids 4.5GB CUDA bloat)
# 3. Install remaining dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Pre-download and bake ML models into the image for 100% offline runtime
COPY scripts/download_models.py scripts/
RUN python scripts/download_models.py

# Copy application source code
COPY . .

# Ensure desktop output directory exists inside container
RUN mkdir -p /root/Desktop/REDACT_Outputs

EXPOSE 8000

# Healthcheck to verify the web app responds
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" || exit 1

CMD ["python", "server.py", "8000"]
