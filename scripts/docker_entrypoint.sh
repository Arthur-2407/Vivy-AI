#!/bin/bash
set -e

echo "============================================================"
echo "  Vivy-AI Production Container Runtime"
echo "  Architecture: Linux Container | Port: 8080"
echo "============================================================"

# Ensure shared and persistent data directories exist
mkdir -p /app/shared /app/database /app/transcripts /app/recordings /app/logs
mkdir -p /data/shared /data/database /data/transcripts /data/logs

# Initialize status file
echo "ready" > /app/shared/status.txt

# Run canonical architecture validator
echo "[Vivy Container] Validating architecture integrity..."
python3 architecture_validator.py || echo "[Warning] Architecture validator reported non-fatal items."

# Execute runtime
echo "[Vivy Container] Launching Vivy AI Runtime Core..."
exec python3 run_vivy.py
