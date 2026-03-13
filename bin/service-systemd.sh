#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="forge"
UNIT_FILE="$HOME/.config/systemd/user/${SERVICE_NAME}.service"
FORGE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

usage() {
    echo "Usage: $0 {register|unregister|enable|disable|start|stop|restart|status|logs}"
    exit 1
}

cmd_register() {
    mkdir -p "$(dirname "$UNIT_FILE")"
    cat > "$UNIT_FILE" <<EOF
[Unit]
Description=Forge - Linear-driven AI agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=${FORGE_ROOT}/bin/daemon.sh
WorkingDirectory=${FORGE_ROOT}
EnvironmentFile=${FORGE_ROOT}/config/forge.env
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    echo "Registered ${SERVICE_NAME} service"
}

cmd_unregister() {
    if [ -f "$UNIT_FILE" ]; then
        systemctl --user stop "$SERVICE_NAME" 2>/dev/null || true
        systemctl --user disable "$SERVICE_NAME" 2>/dev/null || true
        rm "$UNIT_FILE"
        systemctl --user daemon-reload
        echo "Unregistered ${SERVICE_NAME} service"
    else
        echo "Service not registered"
    fi
}

cmd_enable() {
    systemctl --user enable "$SERVICE_NAME"
    echo "Enabled ${SERVICE_NAME} (will start on login)"
}

cmd_disable() {
    systemctl --user disable "$SERVICE_NAME"
    echo "Disabled ${SERVICE_NAME}"
}

cmd_start() {
    systemctl --user start "$SERVICE_NAME"
    echo "Started ${SERVICE_NAME}"
}

cmd_stop() {
    systemctl --user stop "$SERVICE_NAME"
    echo "Stopped ${SERVICE_NAME}"
}

cmd_restart() {
    systemctl --user restart "$SERVICE_NAME"
    echo "Restarted ${SERVICE_NAME}"
}

cmd_status() {
    systemctl --user status "$SERVICE_NAME"
}

cmd_logs() {
    journalctl --user -u "$SERVICE_NAME" -f
}

[ $# -lt 1 ] && usage

case "$1" in
    register)   cmd_register ;;
    unregister) cmd_unregister ;;
    enable)     cmd_enable ;;
    disable)    cmd_disable ;;
    start)      cmd_start ;;
    stop)       cmd_stop ;;
    restart)    cmd_restart ;;
    status)     cmd_status ;;
    logs)       cmd_logs ;;
    *)          usage ;;
esac
