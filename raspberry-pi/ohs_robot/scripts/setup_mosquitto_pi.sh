#!/usr/bin/env bash
set -euo pipefail

sed -i '/^listener 9001 0\.0\.0\.0$/d;/^protocol websockets$/d' /etc/mosquitto/mosquitto.conf

cat >/etc/mosquitto/conf.d/ohs_robot.conf <<'EOF'
per_listener_settings true

listener 1883 0.0.0.0
allow_anonymous true

listener 9001 0.0.0.0
protocol websockets
allow_anonymous true
EOF

systemctl restart mosquitto
systemctl status mosquitto --no-pager