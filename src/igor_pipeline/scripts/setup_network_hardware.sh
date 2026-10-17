#!/usr/bin/env bash
# Configures Ethernet interface for high-speed Jetson <-> DE10-Nano streaming
set -e

IFACE=${1:-"eth0"}
IP_ADDR=${2:-"192.168.1.10/24"}

echo "Configuring network interface $IFACE with IP $IP_ADDR..."

if command -v ip >/dev/null 2>&1; then
    sudo ip link set "$IFACE" up
    sudo ip addr add "$IP_ADDR" dev "$IFACE" 2>/dev/null || true
    echo "Interface $IFACE configured successfully."
else
    echo "Warning: 'ip' command not found. Please configure $IFACE manually."
fi
