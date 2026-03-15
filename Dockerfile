# Use Python 3.12 slim as base
FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# Install system dependencies (ffmpeg is critical for rendering)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and default assets
COPY pb_worker.py pb_client.py ./
COPY slideshow_engine/ ./slideshow_engine/
COPY slideshow_moviepy.py ./

# Copy default assets (bundled into the image)
COPY assets/ ./assets/
COPY bg_music.mp3 ./
COPY logo.webp ./
COPY arrow.png ./

# Environment variable defaults (overridden by K8s)
ENV PB_URL=http://localhost:8090
ENV MAX_WORKERS=0
ENV POLL_INTERVAL=5
ENV LEASE_SECONDS=600
ENV BASE_TMP=/tmp/video-jobs

# Worker is a long-running process, no port exposed
CMD ["python", "pb_worker.py"]
