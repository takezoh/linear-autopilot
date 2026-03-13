#!/usr/bin/env bash
set -euo pipefail

LABEL="com.forge.daemon"
PLIST_FILE="$HOME/Library/LaunchAgents/${LABEL}.plist"
FORGE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${FORGE_ROOT}/logs"

usage() {
    echo "Usage: $0 {register|unregister|enable|disable|start|stop|restart|status|logs}"
    exit 1
}

cmd_register() {
    mkdir -p "$(dirname "$PLIST_FILE")" "$LOG_DIR"
    cat > "$PLIST_FILE" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${FORGE_ROOT}/bin/daemon.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${FORGE_ROOT}</string>
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/launchd-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/launchd-stderr.log</string>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
</dict>
</plist>
EOF
    echo "Registered ${LABEL}"
}

cmd_unregister() {
    if [ -f "$PLIST_FILE" ]; then
        launchctl bootout "gui/$(id -u)" "$PLIST_FILE" 2>/dev/null || true
        rm "$PLIST_FILE"
        echo "Unregistered ${LABEL}"
    else
        echo "Service not registered"
    fi
}

cmd_enable() {
    launchctl bootstrap "gui/$(id -u)" "$PLIST_FILE"
    echo "Enabled ${LABEL}"
}

cmd_disable() {
    launchctl bootout "gui/$(id -u)" "$PLIST_FILE"
    echo "Disabled ${LABEL}"
}

cmd_start() {
    launchctl kickstart "gui/$(id -u)/${LABEL}"
    echo "Started ${LABEL}"
}

cmd_stop() {
    launchctl kill SIGTERM "gui/$(id -u)/${LABEL}"
    echo "Stopped ${LABEL}"
}

cmd_restart() {
    cmd_stop 2>/dev/null || true
    sleep 1
    cmd_start
}

cmd_status() {
    launchctl print "gui/$(id -u)/${LABEL}"
}

cmd_logs() {
    tail -f "$LOG_DIR/launchd-stdout.log" "$LOG_DIR/launchd-stderr.log"
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
