import { api, exigirRol, suscribir } from "/js/api.js";
import { $, el, dinero, chipEstado, toast, barraSuperior, temaActual, segundosHasta } from "/js/ui.js";
import { crearMapa, encuadrar, ponerComercio, ponerDestino, ponerRepartidor, moverSuave, dibujarRuta } from "/js/mapa.js";

const yo = exigirRol("courier");
barraSuperior("Repartidor");
const raiz = $("#raiz");
const mapaCaja = el("div", { class: "mapa-caja alto" }, el("div", { class: "mapa-interno", id: "mapa" }));
const panel = el("div", { class: "apilado", style: "margin-top:14px", "aria-live": "polite" });
raiz.replaceChildren(el("h1", {}, "Tu turno"), el("p", { class: "suave" }, "Es una demo: podés usar los botones sin moverte. Para mover tu moto, tocá el mapa."), mapaCaja, panel);

const mapa = await crearMapa("mapa", { tema: temaActual(), centro: [-56.17, -34.905], zoom: 12.2 });
let miMarcador = null, miPos = null;
let estado = "offline", ofertas = [], activo = null, cerrarStream = null, pedidoAbierto = null, datosPedido = null;
const marcasPedido = { comercio: null, destino: null };

async function enviarPosicion(lngLat) {
  try {
    await api("/courier/location", { metodo: "POST", cuerpo: { lat: lngLat[1], lon: lngLat[0] } });
    const st = await api("/courier/status");   // el servidor ajusta mi posición a la calle más cercana
    lngLat = st.lat != null ? [st.lon, st.lat] : lngLat;
    miPos = lngLat;
    if (miMarcador) moverSuave(miMarcador, lngLat); else miMarcador = ponerRepartidor(mapa, lngLat, "Yo");
    miMarcador.getElement().classList.toggle("ocupado", estado === "busy");
    pintarPanel();
  } catch (e) { toast(e.message, "error"); }
}
mapa.on("click", (e) => enviarPosicion([e.lngLat.lng, e.lngLat.lat]));

async function cambiarEstado(nuevo) {
  try { await api("/courier/status", { metodo: "POST", cuerpo: { status: nuevo } }); estado = nuevo; pintarPanel(); }
  catch (e) { toast(e.message, "error"); }
}
async function responder(oferta, aceptar) {
  try {
    await api(`/courier/offers/${oferta.id}/${aceptar ? "accept" : "reject"}`, { metodo: "POST" });
    toast(aceptar ? "¡Pedido aceptado!" : "Oferta rechazada", aceptar ? "ok" : "");
  } catch (e) { toast(e.message, "error"); }
  await actualizar();
}
async function pedirPrueba(boton) {
  boton.disabled = true;
  try { await api("/demo/simulate-order", { metodo: "POST" }); toast("Te mandamos un pedido de prueba: en unos segundos llega la oferta", "ok"); }
  catch (e) { toast(e.message, "error"); }
  boton.disabled = false;
}
async function avanzar(accionNombre) {
  try { await api(`/courier/orders/${activo.id}/${accionNombre}`, { metodo: "POST" }); await actualizar(); }
  catch (e) { toast(e.message, "error"); await actualizar(); }
}

function pintarPanel() {
  const hijos = [];
  hijos.push(el("div", { class: "tarjeta fila" },
    el("div", { class: "interruptor" }, el("b", {}, estado === "offline" ? "Desconectado" : estado === "busy" ? "Con un pedido" : "Disponible"),
      estado === "busy" ? null : el("span", { class: `chip ${estado === "available" ? "exito" : ""}` }, estado === "available" ? "Recibiendo ofertas" : "Sin ofertas")),
    estado === "busy" ? null : el("button", { class: "btn chico", type: "button", disabled: estado === "offline" && !miPos, onclick: () => cambiarEstado(estado === "available" ? "offline" : "available") },
      estado === "available" ? "Desconectarme" : "Ponerme disponible")));
  if (!miPos) hijos.push(el("div", { class: "vacio" }, "1. Tocá el mapa para indicar dónde estás. 2. Ponete disponible. 3. Pedí un pedido de prueba."));
  else if (estado === "offline") hijos.push(el("div", { class: "vacio" }, "Ya estás en el mapa. Ahora tocá «Ponerme disponible» para recibir ofertas."));

  if (activo) {
    const enCamino = activo.status === "en_camino";
    hijos.push(el("div", { class: "tarjeta apilado" },
      el("div", { class: "fila" }, el("b", {}, enCamino ? "Llevá el pedido al cliente" : "Retirá el pedido en el comercio"), chipEstado(activo.status)),
      el("div", { class: "fila" }, el("span", { class: "suave" }, "Tu ganancia"), el("b", { class: "dinero" }, dinero(activo.delivery_fee_cents))),
      el("button", { class: "btn ancho", type: "button", onclick: () => avanzar(enCamino ? "delivered" : "picked-up") }, enCamino ? "Entregué el pedido" : "Retiré el pedido")));
  } else if (estado === "available") {
    if (!ofertas.length) hijos.push(el("div", { class: "vacio" }, el("p", { style: "margin:0 0 10px" }, "Esperando pedidos cerca tuyo…"),
      el("button", { class: "btn", type: "button", onclick: (e) => pedirPrueba(e.currentTarget) }, "Mandarme un pedido de prueba")));
    for (const o of ofertas) {
      const falta = segundosHasta(o.expires_at);
      hijos.push(el("div", { class: "tarjeta apilado" },
        el("div", { class: "fila" }, el("div", {}, el("b", {}, o.merchant_name), el("div", { class: "suave" }, o.merchant_address)), el("div", { class: "cuenta", "aria-label": `${falta} segundos para responder` }, `${falta}s`)),
        el("div", { class: "fila suave" }, el("span", {}, `Entrega en: ${o.delivery_address}`), el("span", {}, o.distance_m != null ? `${(o.distance_m / 1000).toFixed(1)} km al comercio` : "")),
        el("div", { class: "fila" }, el("span", { class: "suave" }, "Ganancia"), el("b", { class: "dinero" }, dinero(o.fee_cents))),
        el("div", { class: "fila" }, el("button", { class: "btn", style: "flex:1", type: "button", onclick: () => responder(o, true) }, "Aceptar"),
          el("button", { class: "btn secundario", style: "flex:1", type: "button", onclick: () => responder(o, false) }, "Rechazar"))));
    }
  }
  panel.replaceChildren(...hijos);
}

function mostrarPedido(d) {
  datosPedido = d;
  const c = d.merchant, dst = d.destino;
  marcasPedido.comercio ??= ponerComercio(mapa, [c.lon, c.lat], "Comercio");
  marcasPedido.destino ??= ponerDestino(mapa, [dst.lon, dst.lat], "Cliente");
  const dibujar = () => dibujarRuta(mapa, d.route);   // ruta por calles, calculada por el servidor
  mapa.loaded() ? dibujar() : mapa.once("load", dibujar);
  if (pedidoAbierto && !mapa._encuadradoPedido) { encuadrar(mapa, [[c.lon, c.lat], [dst.lon, dst.lat], ...(miPos ? [miPos] : [])], { abajo: 40, arriba: 40, lados: 60 }); mapa._encuadradoPedido = true; }
}
function limpiarPedido() {
  cerrarStream?.(); cerrarStream = null; pedidoAbierto = null; datosPedido = null; mapa._encuadradoPedido = false;
  for (const k of Object.keys(marcasPedido)) { marcasPedido[k]?.remove(); marcasPedido[k] = null; }
  if (mapa.getLayer("ruta")) { mapa.removeLayer("ruta"); mapa.removeLayer("ruta-borde"); mapa.removeSource("ruta"); }
}

let ocupadoActualizando = false;
async function actualizar() {
  if (ocupadoActualizando) return;
  ocupadoActualizando = true;
  try {
    const [st, of, pedidos] = await Promise.all([api("/courier/status"), api("/courier/offers"), api("/orders")]);
    estado = st.status; ofertas = of;
    if (!miPos && st.lat != null) {   // primera vez: dibujo mi moto donde el servidor dice que estoy
      miPos = [st.lon, st.lat];
      miMarcador = ponerRepartidor(mapa, miPos, "Yo");
      mapa.jumpTo({ center: miPos, zoom: 14.2 });
    }
    activo = pedidos.find((p) => ["asignado", "en_camino"].includes(p.status)) ?? null;
    miMarcador?.getElement().classList.toggle("ocupado", estado === "busy");
    if (activo && pedidoAbierto !== activo.id) {
      limpiarPedido(); pedidoAbierto = activo.id;
      cerrarStream = suscribir(`/orders/${activo.id}/live`, { estado: mostrarPedido, posicion: (p) => p.route && dibujarRuta(mapa, p.route) });
    }
    if (!activo && pedidoAbierto) limpiarPedido();
    pintarPanel();
  } catch (e) { if (e.estado !== 401) toast(e.message, "error"); }
  ocupadoActualizando = false;
}

await actualizar();
setInterval(actualizar, 2000);
setInterval(() => { if (ofertas.length && !activo) pintarPanel(); }, 1000);   // la cuenta regresiva baja cada segundo
