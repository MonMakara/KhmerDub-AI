#!/usr/bin/env bash
# KhmerDub AI — Launch VoxCPM2 GPU Inference Worker
# Runs in the isolated 'voxcpm-bench' conda environment on port 8002.

set -e

WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="/home/mark/miniconda3/envs/voxcpm-bench/bin/python"
if [ ! -f "${PYTHON_BIN}" ]; then
    PYTHON_BIN="/home/mark/miniforge3/envs/voxcpm-bench/bin/python"
fi
WORKER_SCRIPT="${WORKSPACE_DIR}/backend/app/services/voice/worker.py"

if [ ! -f "${PYTHON_BIN}" ]; then
    echo "[ERROR] Conda environment 'voxcpm-bench' python not found at: ${PYTHON_BIN}"
    exit 1
fi

export PYTHONPATH="${WORKSPACE_DIR}:${WORKSPACE_DIR}/backend:${PYTHONPATH}"
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
export VOXCPM_PORT="${VOXCPM_PORT:-8002}"
export VOXCPM_HOST="${VOXCPM_HOST:-0.0.0.0}"
export VOXCPM_INTERNAL_SECRET="${VOXCPM_INTERNAL_SECRET:-khmerdub-voxcpm-internal-auth-token-2026}"

echo "=========================================================="
echo " Starting KhmerDub AI VoxCPM2 GPU Inference Worker"
echo " Workspace: ${WORKSPACE_DIR}"
echo " Port:      ${VOXCPM_PORT}"
echo " Python:    ${PYTHON_BIN}"
echo "=========================================================="

exec "${PYTHON_BIN}" "${WORKER_SCRIPT}"
