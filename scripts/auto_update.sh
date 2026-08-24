#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${PAPER_LENS_LOG_DIR:-${PROJECT_DIR}/data/logs}"
LOCK_FILE="${PAPER_LENS_LOCK_FILE:-${PROJECT_DIR}/data/update.lock}"
mkdir -p "${LOG_DIR}"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "[$(date --iso-8601=seconds)] 已有更新任务运行，本轮跳过" >> "${LOG_DIR}/update.log"
  exit 0
fi

TRANSLATE_PROVIDER="${PAPER_LENS_TRANSLATE:-none}"
TRANSLATE_LIMIT="${PAPER_LENS_TRANSLATE_LIMIT:-20}"
PER_QUERY="${PAPER_LENS_PER_QUERY:-40}"

{
  echo "[$(date --iso-8601=seconds)] 开始同步"
  python3 "${PROJECT_DIR}/scripts/update_papers.py" \
    --per-query "${PER_QUERY}" \
    --translate "${TRANSLATE_PROVIDER}" \
    --translate-limit "${TRANSLATE_LIMIT}"
  echo "[$(date --iso-8601=seconds)] 同步完成"
} >> "${LOG_DIR}/update.log" 2>&1
