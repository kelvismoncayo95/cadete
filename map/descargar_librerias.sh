#!/usr/bin/env bash
# Descarga (una vez) las librerías y tipografías del mapa para servirlas desde el propio proyecto.
# Así la demo no depende de CDNs de terceros. Versiones fijas, con varios meses de antigüedad.
#   MapLibre GL JS 5.24.0 (BSD-3) · PMTiles 4.5.0 (BSD-3) · Noto Sans (SIL OFL, vía protomaps/basemaps-assets)
set -euo pipefail
cd "$(dirname "$0")/../web"
curl -fsS -o vendor/maplibre-gl.js  https://unpkg.com/maplibre-gl@5.24.0/dist/maplibre-gl.js
curl -fsS -o vendor/maplibre-gl.css https://unpkg.com/maplibre-gl@5.24.0/dist/maplibre-gl.css
curl -fsS -o vendor/pmtiles.js      https://unpkg.com/pmtiles@4.5.0/dist/pmtiles.js
curl -fsS -o vendor/LICENSE-maplibre-gl.txt https://unpkg.com/maplibre-gl@5.24.0/LICENSE.txt || true
curl -fsS -o vendor/LICENSE-pmtiles.txt     https://raw.githubusercontent.com/protomaps/PMTiles/main/LICENSE || true
BASE=https://protomaps.github.io/basemaps-assets/fonts
for fuente in "Noto Sans Regular" "Noto Sans Medium" "Noto Sans Italic"; do
  mkdir -p "map/fonts/$fuente"
  for rango in 0-255 256-511 8192-8447; do   # latín, latín extendido y puntuación (comillas, guiones)
    curl -fsS -o "map/fonts/$fuente/$rango.pbf" "$BASE/${fuente// /%20}/$rango.pbf"
  done
done
curl -fsS -o map/fonts/OFL.txt https://raw.githubusercontent.com/protomaps/basemaps-assets/main/fonts/OFL.txt || true
echo "Listo."
