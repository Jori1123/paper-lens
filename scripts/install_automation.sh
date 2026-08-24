#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
USER_SYSTEMD_DIR="${HOME}/.config/systemd/user"
ENV_FILE="${PROJECT_DIR}/.env.update"

mkdir -p "${USER_SYSTEMD_DIR}"

cat > "${USER_SYSTEMD_DIR}/paper-lens-update.service" <<EOF
[Unit]
Description=Paper Lens academic paper sync
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=${PROJECT_DIR}
EnvironmentFile=-${ENV_FILE}
ExecStart=${PROJECT_DIR}/scripts/auto_update.sh
EOF

cat > "${USER_SYSTEMD_DIR}/paper-lens-update.timer" <<'EOF'
[Unit]
Description=Update Paper Lens every six hours

[Timer]
OnBootSec=5min
OnUnitActiveSec=6h
RandomizedDelaySec=10min
Persistent=true

[Install]
WantedBy=timers.target
EOF

chmod +x "${PROJECT_DIR}/scripts/auto_update.sh"
systemctl --user daemon-reload
systemctl --user enable --now paper-lens-update.timer

echo "自动更新已启用（每 6 小时执行一次）。"
echo "状态：systemctl --user status paper-lens-update.timer"
echo "日志：${PROJECT_DIR}/data/logs/update.log"
echo "配置：${ENV_FILE}（可选）"
