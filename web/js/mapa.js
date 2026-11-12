// Mapa propio de Montevideo: MapLibre GL JS + archivo PMTiles servido por nosotros.
// Las librerías (maplibregl y pmtiles) se cargan antes con <script> y quedan como globales.

const ORIGEN = location.origin;
const ACENTO = { claro: "#C2410C", oscuro: "#FB923C" };
const MOVIMIENTO_REDUCIDO = matchMedia("(prefers-reduced-motion: reduce)").matches;
let protocoloRegistrado = false;

export function temaDelSistema() {
  return matchMedia("(prefers-color-scheme: dark)").matches ? "oscuro" : "claro";
}

function registrarPMTiles() {
  if (protocoloRegistrado) return;
  maplibregl.addProtocol("pmtiles", new pmtiles.Protocol().tile);
  protocoloRegistrado = true;
}

async function cargarEstilo(tema) {
  const texto = await (await fetch(`/map/style-${tema}.json`)).text();
  return JSON.parse(texto.replaceAll("__ORIGEN__", ORIGEN));
}

/** Crea el mapa. `alCargar(mapa)` se llama al terminar de cargar el estilo, y de nuevo cada vez que cambia el tema
 *  (al cambiar de estilo MapLibre borra las capas que agregamos nosotros, hay que volver a dibujarlas). */
export async function crearMapa(contenedor, { tema = temaDelSistema(), centro = [-56.17, -34.905], zoom = 12.5, alCargar } = {}) {
  registrarPMTiles();
  document.documentElement.dataset.tema = tema;
  const mapa = new maplibregl.Map({
    container: contenedor,
    style: await cargarEstilo(tema),
    center: centro,
    zoom,
    minZoom: 9.5,
    maxZoom: 18,
    maxBounds: [[-56.6, -35.05], [-55.9, -34.65]],   // no se sale de la zona de Montevideo
    attributionControl: false,
    dragRotate: false,
    pitchWithRotate: false,
  });
  mapa.addControl(new maplibregl.AttributionControl({ compact: false }));   // © OpenStreetMap, siempre visible
  mapa.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");   // arriba: la hoja inferior no los tapa
  mapa.temaActual = tema;
  mapa.alCargar = alCargar;
  mapa.on("error", (e) => console.error("mapa:", e.error?.message ?? e));   // errores de teselas, estilo, tipografías
  mapa.on("load", () => alCargar?.(mapa));
  return mapa;
}

export async function cambiarTema(mapa, tema) {
  document.documentElement.dataset.tema = tema;
  mapa.temaActual = tema;
  mapa.setStyle(await cargarEstilo(tema));
  mapa.once("style.load", () => mapa.alCargar?.(mapa));
}

/** Encuadra el mapa para que se vean todos los puntos. `abajo` deja lugar a la hoja inferior (en píxeles). */
export function encuadrar(mapa, puntos, { abajo = 180, arriba = 80, lados = 70, animar = false } = {}) {
  const caja = puntos.reduce((c, p) => c.extend(p), new maplibregl.LngLatBounds(puntos[0], puntos[0]));
  mapa.fitBounds(caja, { padding: { top: arriba, bottom: abajo, left: lados, right: lados }, maxZoom: 16, duration: animar ? 600 : 0 });
}

// ---------- Marcadores ----------
const ICONOS = {
  moto: '<svg viewBox="0 0 24 24"><circle cx="5.5" cy="16.5" r="3"/><circle cx="18.5" cy="16.5" r="3"/><path d="M8.5 16.5h5l2.5-7h-3M15 9.5l1.5-3H19M9 12.5h4"/></svg>',
  tienda: '<svg viewBox="0 0 24 24"><path d="M4 9l1.5-5h13L20 9M4 9v10h16V9M4 9c0 2 3 2 4 0 1 2 3 2 4 0 1 2 3 2 4 0 1 2 4 2 4 0M10 19v-5h4v5"/></svg>',
  casa: '<svg viewBox="0 0 24 24"><path d="M4 11l8-7 8 7M6 10v10h12V10M10 20v-6h4v6"/></svg>',
};

function crearMarcador(clase, icono, texto) {
  const el = document.createElement("div");
  el.className = `marcador ${clase}`;
  el.setAttribute("role", "img");
  el.setAttribute("aria-label", texto);
  el.innerHTML = `<div class="icono">${ICONOS[icono]}</div><span class="etiqueta">${texto}</span>`;
  return el;
}

export function ponerRepartidor(mapa, lngLat, texto = "Repartidor") {
  return new maplibregl.Marker({ element: crearMarcador("repartidor", "moto", texto) }).setLngLat(lngLat).addTo(mapa);
}
export function ponerComercio(mapa, lngLat, texto) {
  return new maplibregl.Marker({ element: crearMarcador("comercio", "tienda", texto) }).setLngLat(lngLat).addTo(mapa);
}
export function ponerDestino(mapa, lngLat, texto = "Tu casa") {
  return new maplibregl.Marker({ element: crearMarcador("destino", "casa", texto) }).setLngLat(lngLat).addTo(mapa);
}

/** Desliza el marcador hasta la nueva posición (no salta). Con «reducir movimiento», salta directo. */
export function moverSuave(marcador, destino, ms = 900) {
  const [lng0, lat0] = marcador.getLngLat().toArray();
  if (MOVIMIENTO_REDUCIDO || ms <= 0) { marcador.setLngLat(destino); return; }
  const t0 = performance.now();
  cancelAnimationFrame(marcador._animacion);
  const paso = (ahora) => {
    const k = Math.min(1, (ahora - t0) / ms);
    const suave = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;   // acelera y frena
    marcador.setLngLat([lng0 + (destino[0] - lng0) * suave, lat0 + (destino[1] - lat0) * suave]);
    if (k < 1) marcador._animacion = requestAnimationFrame(paso);
  };
  marcador._animacion = requestAnimationFrame(paso);
}

/** Dibuja (o actualiza) la ruta: línea naranja de 5 px con borde blanco. */
export function dibujarRuta(mapa, coordenadas) {
  const datos = { type: "Feature", geometry: { type: "LineString", coordinates: coordenadas } };
  if (mapa.getSource("ruta")) { mapa.getSource("ruta").setData(datos); return; }
  mapa.addSource("ruta", { type: "geojson", data: datos });
  const claro = mapa.temaActual === "claro";
  const comunes = { "line-cap": "round", "line-join": "round" };
  mapa.addLayer({ id: "ruta-borde", type: "line", source: "ruta", layout: comunes,
    paint: { "line-color": claro ? "#FFFFFF" : "#14161A", "line-width": 9 } });
  mapa.addLayer({ id: "ruta", type: "line", source: "ruta", layout: comunes,
    paint: { "line-color": ACENTO[mapa.temaActual], "line-width": 5 } });
}
