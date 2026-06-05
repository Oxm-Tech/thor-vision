#!/bin/bash
# Verifica conectividad RTSP de todas las cámaras
CAMERAS=(
  "113:192.168.20.113"
  "115:192.168.20.115"
  "118:192.168.20.118"
  "120:192.168.20.120"
  "189:192.168.20.189"
  "191:192.168.20.191"
  "215:192.168.20.215"
  "227:192.168.20.227"
  "228:192.168.20.228"
  "236:192.168.20.236"
)

echo "=== THOR Vision — Camera Check ==="
for entry in "${CAMERAS[@]}"; do
  name="${entry%%:*}"
  ip="${entry##*:}"
  if nc -z -w2 "$ip" 554 2>/dev/null; then
    echo "  ✓ cam-$name  $ip:554 REACHABLE"
  else
    echo "  ✗ cam-$name  $ip:554 UNREACHABLE"
  fi
done
