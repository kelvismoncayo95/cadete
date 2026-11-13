#!/usr/bin/env bash
# Prepara los datos de ruteo de OSRM (calles de Uruguay, de OpenStreetMap vía Geofabrik, licencia ODbL).
# Uso: ./preparar.sh [AAMMDD]    (sin fecha: la última publicada)
# Genera routing/data/uruguay.osrm* (grande: no va a git). Tarda unos minutos y usa ~1-2 GB de RAM.
set -euo pipefail
cd "$(dirname "$0")/data"
IMAGEN="ghcr.io/project-osrm/osrm-backend:v26.7.0-debian"
URL="https://download.geofabrik.de/south-america/uruguay-latest.osm.pbf"
[ -n "${1:-}" ] && URL="https://download.geofabrik.de/south-america/uruguay-$1.osm.pbf"
[ -f uruguay.osm.pbf ] || curl -fL --retry 3 -o uruguay.osm.pbf "$URL"
# El perfil «car» respeta sentidos únicos, giros prohibidos y tipos de calle.
docker run --rm -v "$PWD:/data" "$IMAGEN" osrm-extract -p /opt/car.lua /data/uruguay.osm.pbf
docker run --rm -v "$PWD:/data" "$IMAGEN" osrm-partition /data/uruguay.osrm
docker run --rm -v "$PWD:/data" "$IMAGEN" osrm-customize /data/uruguay.osrm
echo "Listo: routing/data/uruguay.osrm"
