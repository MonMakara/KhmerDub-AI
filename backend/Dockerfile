FROM python:3.11-slim

# Install system dependencies including FFmpeg for media processing and Khmer fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    curl \
    tzdata \
    fontconfig \
    fonts-khmeros \
    fonts-noto-core \
    libicu-dev \
    pkg-config \
    g++ \
    && fc-cache -f -v \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PIP_DEFAULT_TIMEOUT=1000

# Pre-install CPU-only PyTorch (~180 MB) to avoid downloading 2.5+ GB of unnecessary NVIDIA CUDA wheels
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch>=2.2.0"

# Install remaining Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Isolated audio cleaning environment for Demucs speech/music separation
RUN python -m venv --system-site-packages /opt/audio-cleaning-env \
    && /opt/audio-cleaning-env/bin/pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torchaudio \
    && /opt/audio-cleaning-env/bin/pip install --no-cache-dir 'numpy<2' 'soundfile>=0.12,<0.14' demucs==4.0.1

# Copy backend source
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
