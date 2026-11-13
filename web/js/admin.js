import { api, suscribir } from "/js/api.js";
import { $, el, toast, barraSuperior, temaActual } from "/js/ui.js";
import { exigirRol } from "/js/api.js";
import { crearMapa, ponerRepartidor, moverSuave } from "/js/mapa.js";

exigirRol("admin");
barraSuperior("Administrador");
const raiz = $("#raiz");
raiz.className = ""; raiz.replaceChildren(el("div", { class: "mapa-completo", id: "mapa", style: "top:57px" }));
const panel = el("section", { class: "tarjeta panel-admin", "aria-live": "polite" });
document.body.append(panel);

const repartidores = new Map();   // id → { marcador, estado }
const pedidos = new Map();        // id → datos del pedido (solo los activos)
let conectado = false, vistoSistema = null;
const TERMINALES = ["entregado", "rechazado", "cancelado"];

const mapa = await crearMapa("mapa", { tema: temaActual(), centro: [-56.17, -34.9], zoom: 12.2, alCargar: () => dibujarPedidos() });
window.cadeteMapa = mapa;

function dibujarPedidos() {
  const lineas = [], puntos = [];
  for (const p of pedidos.values()) {
    lineas.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: p.route ?? [[p.merchant.lon, p.merchant.lat], [p.destino.lon, p.destino.lat]] } });
    puntos.push({ type: "Feature", properties: { estado: p.status }, geometry: { type: "Point", coordinates: [p.destino.lon, p.destino.lat] } });
  }
  const datos = (features) => ({ type: "FeatureCollection", features });
  if (!mapa.getSource("pedidos-lineas")) {
    const acento = temaActual() === "claro" ? "#C2410C" : "#FB923C";
    mapa.addSource("pedidos-lineas", { type: "geojson", data: datos(lineas) });
    mapa.addSource("pedidos-destinos", { type: "geojson", data: datos(puntos) });
    mapa.addLayer({ id: "pedidos-lineas", type: "line", source: "pedidos-lineas", paint: { "line-color": acento, "line-width": 2, "line-opacity": 0.55, "line-dasharray": [2, 2] } });
    mapa.addLayer({ id: "pedidos-destinos", type: "circle", source: "pedidos-destinos", paint: { "circle-radius": 6, "circle-color": acento, "circle-stroke-color": "#fff", "circle-stroke-width": 2 } });
  } else {
    mapa.getSource("pedidos-lineas").setData(datos(lineas));
    mapa.getSource("pedidos-destinos").setData(datos(puntos));
  }
}

function pintarPanel() {
  const libres = [...repartidores.values()].filter((r) => r.estado === "available").length;
  const ocupados = [...repartidores.values()].filter((r) => r.estado === "busy").length;
  panel.replaceChildren(
    el("div", { class: "fila" }, el("b", {}, "Mapa en vivo"), el("span", { class: `chip ${conectado ? "exito" : "alerta"}` }, conectado ? "En vivo" : "Reconectando…")),
    el("div", { class: "fila", style: "margin-top:10px" }, el("span", {}, "Pedidos activos"), el("b", {}, String(pedidos.size))),
    el("div", { class: "fila" }, el("span", {}, "Repartidores libres"), el("b", {}, String(libres))),
    el("div", { class: "fila" }, el("span", {}, "Repartidores con pedido"), el("b", {}, String(ocupados))),
    el("div", { class: "fila" }, el("span", {}, "Estado del sistema"), el("b", {}, vistoSistema ?? "…")),
    el("div", { class: "leyenda" }, el("span", {}, el("i", { class: "punto", style: "background:var(--acento)" }), "Repartidor libre"),
      el("span", {}, el("i", { class: "punto", style: "background:var(--texto)" }), "Con pedido"), el("span", {}, "Línea: ruta por calles")));
}

function ponerOMoverRepartidor(id, lat, lon, estado) {
  let r = repartidores.get(id);
  if (!r) { r = { marcador: ponerRepartidor(mapa, [lon, lat], estado === "busy" ? "Con pedido" : "Libre"), estado }; r.marcador.getElement().classList.add("pequeno"); repartidores.set(id, r); }
  else moverSuave(r.marcador, [lon, lat], 800);
  r.estado = estado;
  r.marcador.getElement().classList.toggle("ocupado", estado === "busy");
  r.marcador.getElement().querySelector(".etiqueta").textContent = estado === "busy" ? "Con pedido" : estado === "available" ? "Libre" : "Desconectado";
}

function aplicarFoto(d) {   // llega al conectar y cada vez que se reconecta: se rehace todo desde cero
  for (const r of repartidores.values()) r.marcador.remove();
  repartidores.clear(); pedidos.clear();
  for (const c of d.couriers) ponerOMoverRepartidor(c.id, c.lat, c.lon, c.status);
  for (const o of d.orders) pedidos.set(o.order_id, o);
  mapa.loaded() ? dibujarPedidos() : mapa.once("load", dibujarPedidos);
  pintarPanel();
}

suscribir("/admin/live", {
  snapshot: aplicarFoto,
  repartidor: (d) => { ponerOMoverRepartidor(d.courier_id, d.lat, d.lon, d.status); pintarPanel(); },
  estado: (d) => {
    if (TERMINALES.includes(d.status)) pedidos.delete(d.order_id); else pedidos.set(d.order_id, d);
    if (mapa.getSource("pedidos-lineas")) dibujarPedidos();
    pintarPanel();
  },
}, (ok) => { conectado = ok; pintarPanel(); });

async function revisarSistema() {
  try {
    const d = await api("/admin/system");
    vistoSistema = { ok: "Sano", degradado: "Degradado", caido: "Caído" }[d.status] ?? d.status;
    if (d.alertas.pedidos_sin_repartidor) vistoSistema += ` · ${d.alertas.pedidos_sin_repartidor} sin repartidor`;
  } catch { vistoSistema = "Sin conexión"; }
  pintarPanel();
}
await revisarSistema();
setInterval(revisarSistema, 10000);
pintarPanel();
