#!/usr/bin/env bash
# Baja SOLO el recorte de Montevideo (unos 11 MB) del mapa mundial de Protomaps (OpenStreetMap).
# Uso: ./extraer.sh [AAAAMMDD]   (sin fecha: usa la última compilación publicada)
# Licencia de los datos: ODbL. Obligatorio mostrar "© OpenStreetMap" en el mapa.
set -euo pipefail
cd "$(dirname "$0")"
FECHA="${1:-$(curl -sS https://build-metadata.protomaps.dev/builds.json | python3 -c 'import sys,json; print(json.load(sys.stdin)[-1]["key"].removesuffix(".pmtiles"))')}"
echo "Compilación: $FECHA"
./bin/pmtiles extract "https://build.protomaps.com/${FECHA}.pmtiles" ../web/map/montevideo.pmtiles \
  --bbox=-56.50,-35.00,-55.95,-34.70 --maxzoom=15
./bin/pmtiles show ../web/map/montevideo.pmtiles | head -12
