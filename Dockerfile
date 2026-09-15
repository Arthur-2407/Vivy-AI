# syntax=docker/dockerfile:1
FROM python:3.10-slim-bookworm

LABEL maintainer="Arthur-2407" \
      description="Vivy-AI Autonomous Multimodal Runtime" \
      version="2.0.0"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    VIVY_PROCESS_ROLE=runner \
    VIVY_WEB_PORT=8080 \
    VIVY_WEB_HOST=0.0.0.0 \
    VIVY_SHARED_DIR=/app/shared

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    ffmpeg \
    libsndfile1 \
    libgl1 \
    libglib2.0-0 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python production dependencies first for optimal Docker layer caching
COPY requirements-production.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-production.txt

# Copy application source code
COPY . /app/

# Create persistent storage directories and fix permissions
RUN mkdir -p /app/shared /app/database /app/transcripts /app/recordings /app/logs /data && \
    chmod +x /app/scripts/docker_entrypoint.sh

# Expose ports:
# 8080 - Web Dashboard & REST API
# 8765 - Avatar Bridge WebSocket
# 8800 - Vivy Hub WebSocket
# 8766 - Voice Cloning RVC RPC Server
EXPOSE 8080 8765 8800 8766

# Health check against production status endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD curl -f http://127.0.0.1:8080/api/status || exit 1

ENTRYPOINT ["/app/scripts/docker_entrypoint.sh"]
