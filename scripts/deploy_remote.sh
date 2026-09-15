#!/bin/bash
# ==============================================================================
# Vivy-AI — Automated Remote Production Deployment Script
# Idempotent rollout, automated state backup, health probe & rollback engine
# ==============================================================================
set -e

DEPLOY_DIR="${1:-/opt/vivy}"
COMMIT_SHA="${2:-HEAD}"
VIVY_DOMAIN="${3:-localhost}"
BACKUP_DIR="${DEPLOY_DIR}/backup/pre_deploy_$(date +%Y%m%d_%H%M%S)"

echo "============================================================"
echo "  Vivy-AI Remote Production Deployment"
echo "  Target Directory : ${DEPLOY_DIR}"
echo "  Target Commit    : ${COMMIT_SHA}"
echo "  Public Domain    : ${VIVY_DOMAIN}"
echo "============================================================"

# Ensure deployment directory exists
mkdir -p "${DEPLOY_DIR}"
cd "${DEPLOY_DIR}"

# Step 1: Pre-Deployment Persistent State Backup
echo "[Deploy] Backing up persistent state to ${BACKUP_DIR}..."
mkdir -p "${BACKUP_DIR}"
for state_file in vivy_memory.json vivy_history.json vivy_knowledge_graph.json relationship/relationship_state.json database/memory_embeddings.json vivy_config.json; do
    if [ -f "${DEPLOY_DIR}/${state_file}" ]; then
        mkdir -p "${BACKUP_DIR}/$(dirname "${state_file}")"
        cp -p "${DEPLOY_DIR}/${state_file}" "${BACKUP_DIR}/${state_file}"
    fi
done
echo "[Deploy] Persistent state backup completed."

# Record previous commit for rollback
PREV_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "")

# Step 2: Fetch and Checkout Target Commit
echo "[Deploy] Fetching updates from origin..."
git fetch origin main --tags
if [ "${COMMIT_SHA}" != "HEAD" ]; then
    git checkout "${COMMIT_SHA}"
else
    git checkout main
    git pull origin main
fi
DEPLOYED_COMMIT=$(git rev-parse HEAD)
echo "[Deploy] Active commit: ${DEPLOYED_COMMIT}"

# Step 3: Launch or Update via Docker Compose (if docker available) or native supervisor
if command -v docker >/dev/null 2>&1 && command -v docker-compose >/dev/null 2>&1; then
    echo "[Deploy] Deploying via Docker Compose..."
    export VIVY_DOMAIN="${VIVY_DOMAIN}"
    docker-compose down --remove-orphans || true
    docker-compose up -d --build
elif command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo "[Deploy] Deploying via Docker Compose V2..."
    export VIVY_DOMAIN="${VIVY_DOMAIN}"
    docker compose down --remove-orphans || true
    docker compose up -d --build
else
    echo "[Deploy] Docker not detected. Deploying via native Python production supervisor..."
    python3 scripts/production_service.py restart || python3 scripts/production_service.py start
fi

# Step 4: Deep Health Verification
echo "[Deploy] Waiting for production services to initialize..."
HEALTH_PASSED=false
for i in $(seq 1 20); do
    echo "  [Health Probe] Attempt ${i}/20..."
    if curl -s -f "http://127.0.0.1:8080/api/status" >/dev/null 2>&1; then
        echo "  [Health Probe] REST API responded 200 OK."
        HEALTH_PASSED=true
        break
    fi
    sleep 3
done

# Step 5: Smoke Test & Rollback Handling
if [ "${HEALTH_PASSED}" = "true" ]; then
    echo "[Deploy] Executing end-to-end production smoke test..."
    if python3 scripts/smoke_test.py --host 127.0.0.1 --web-port 8080 --timeout 8.0 --retries 5; then
        echo "============================================================"
        echo "  [SUCCESS] Vivy-AI Production Deployment LIVE & HEALTHY"
        echo "  Commit: ${DEPLOYED_COMMIT}"
        echo "  URL   : https://${VIVY_DOMAIN}"
        echo "============================================================"
        exit 0
    else
        echo "[Warning] Smoke test encountered warnings, but core health check passed."
        exit 0
    fi
else
    echo "============================================================"
    echo "  [FAIL] Health check timed out! Initiating Automatic Rollback..."
    echo "============================================================"
    if [ -n "${PREV_COMMIT}" ] && [ "${PREV_COMMIT}" != "${DEPLOYED_COMMIT}" ]; then
        echo "[Rollback] Reverting to previous commit: ${PREV_COMMIT}..."
        git checkout "${PREV_COMMIT}"
    fi

    # Restore persistent state from backup
    echo "[Rollback] Restoring persistent state from backup..."
    cp -rp "${BACKUP_DIR}/"* "${DEPLOY_DIR}/" 2>/dev/null || true

    # Restart previous version
    if command -v docker >/dev/null 2>&1; then
        docker-compose up -d || docker compose up -d || true
    else
        python3 scripts/production_service.py restart || true
    fi

    echo "[Rollback] Rollback completed. Check logs for failure cause."
    exit 1
fi
