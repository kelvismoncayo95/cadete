# Atribuciones y licencias del mapa

| Pieza | Origen | Licencia |
|---|---|---|
| Datos de calles, parques, agua y barrios | © OpenStreetMap contributors, compilados por el Protomaps Basemap (compilación 2026-11-12, recorte de Montevideo con `pmtiles extract`) | ODbL: **atribución obligatoria** («© OpenStreetMap», siempre visible en el mapa) |
| `montevideo.pmtiles` | Obra producida a partir de los datos anteriores | ODbL (Produced Work) |
| MapLibre GL JS 5.24.0 | https://github.com/maplibre/maplibre-gl-js | BSD-3-Clause |
| PMTiles 4.5.0 | https://github.com/protomaps/PMTiles | BSD-3-Clause |
| Tipografías Noto Sans (Regular, Medium, Italic) | https://github.com/protomaps/basemaps-assets | SIL Open Font License 1.1 (`fonts/OFL.txt`) |
| Rutas (OSRM v26.7.0) y sus datos | Motor: https://github.com/Project-OSRM/osrm-backend (BSD-2-Clause). Datos: © OpenStreetMap contributors, extracto de Uruguay de Geofabrik (2026-11-11) | ODbL (la atribución «© OpenStreetMap» del mapa cubre también las rutas) |
| Estilos `style-claro.json` y `style-oscuro.json` | Diseño propio de Cadete (`map/construir_estilo.py`) | Del proyecto |

Cómo se regenera: `map/extraer.sh` (datos), `map/descargar_librerias.sh` (librerías y tipografías),
`python3 map/construir_estilo.py` (estilos).
