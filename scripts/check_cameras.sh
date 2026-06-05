#!/bin/bash
# Verifica conectividad RTSP de todas las cámaras configuradas en cameras.yml
# Uso: ./scripts/check_cameras.sh [IP1] [IP2] ...
#
# Ejemplo con IPs específicas:
#   ./scripts/check_cameras.sh 192.168.1.100 192.168.1.101
#
# O edita el arreglo CAMERAS con las IPs de tu instalación:

CAMERAS=(
  # "nombre:ip"
  # "cam-entrada:192.168.X.X"
  # "cam-interior:192.168.X.X"
)

# Si se pasan IPs como argumentos, usarlas
if [ $# -gt 0 ]; then
  CAMERAS=()
  for ip in "$@"; do
    CAMERAS+=("cam:$ip")
  done
fi

if [ ${#CAMERAS[@]} -eq 0 ]; then
  echo "Uso: $0 [IP1] [IP2] ..."
  echo "  O edita el arreglo CAMERAS en este script."
  exit 1
fi

echo "=== THOR Vision — Camera Check ==="
for entry in "${CAMERAS[@]}"; do
  name="${entry%%:*}"
  ip="${entry##*:}"
  if nc -z -w2 "$ip" 554 2>/dev/null; then
    echo "  ✓ $name  $ip:554 REACHABLE"
  else
    echo "  ✗ $name  $ip:554 UNREACHABLE"
  fi
done
