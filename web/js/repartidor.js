import { api, exigirRol, suscribir } from "/js/api.js";
import { $, el, dinero, chipEstado, toast, barraSuperior, temaActual, segundosHasta } from "/js/ui.js";
import { crearMapa, encuadrar, ponerComercio, ponerDestino, ponerRepartidor, moverSuave, dibujarRuta } from "/js/mapa.js";
import { distanciaM, RADIO_LLEGADA_M, redondear10 } from "/js/geo.js";

const yo = exigirRol("courier");
barraSuperior("Repartidor");
const raiz = $("#raiz");
const mapaCaja = el("div", { class: "mapa-caja alto" }, el("div", { class: "mapa-interno", id: "mapa" }));
const panel = el("div", { class: "apilado", style: "margin-top:14px", "aria-live": "polite" });
const ganado = el("span", { class: "chip exito" }, "Ganado hoy: …");
raiz.replaceChildren(
  el("div", { class: "fila" }, el("h1", {}, "Tu turno"), ganado),
  el("p", { class: "suave" }, "Es una demo: tocá el mapa para moverte, o usá «Conducir» para que la moto vaya sola por las calles."),
  mapaCaja, panel);

const mapa = await crearMapa("mapa", { tema: temaActual(), centro: [-56.17, -34.905], zoom: 12.2 });
let miMarcador = null, miPos = null;
let estado = "offline", ofertas = [], activo = null, cerrarStream = null, pedidoAbierto = null, datosPedido = null;
let pilotoActivo = false, ultimoActivo = null, preparando = [], yaListos = null;
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
    toast(aceptar ? "¡Pedido aceptado! Andá al comercio." : "Oferta rechazada", aceptar ? "ok" : "");
  } catch (e) { toast(e.message, "error"); }
  await actualizar();
}
async function avanzar(accionNombre) {
  const id = activo.id, pago = activo.courier_pay_cents;
  try {
    await api(`/courier/orders/${id}/${accionNombre}`, { metodo: "POST" });
    if (accionNombre === "delivered") toast(`¡Entregado! Cobraste ${dinero(pago ?? 0)}`, "ok");
    if (accionNombre !== "picked-up") { pilotoActivo = false; await api("/courier/autopilot", { metodo: "POST", cuerpo: { activo: false } }); }
    await actualizar();
  } catch (e) { toast(e.message, "error"); await actualizar(); }
}
async function alternarPiloto() {
  pilotoActivo = !pilotoActivo;
  try { await api("/courier/autopilot", { metodo: "POST", cuerpo: { activo: pilotoActivo } }); }
  catch (e) { pilotoActivo = !pilotoActivo; toast(e.message, "error"); }
  pintarPanel();
}

// Distancia de la moto al lugar al que tiene que ir ahora (comercio o cliente), con lo que manda el servidor.
function distanciaAlObjetivo() {
  const c = datosPedido?.courier;
  if (!c || !activo) return null;
  const objetivo = activo.status === "asignado" ? datosPedido.merchant : datosPedido.destino;
  return distanciaM(c.lat, c.lon, objetivo.lat, objetivo.lon);
}

// Comercios que están preparando un pedido (o ya lo tienen listo): se ven en el mapa y en una lista.
function tarjetasComercios() {
  if (!preparando.length) return [];
  const km = (m) => (m == null ? "?" : (m / 1000).toFixed(1).replace(".", ","));
  return [el("div", { class: "tarjeta apilado" },
    el("b", {}, "Comercios con pedidos"),
    ...preparando.map((c) => el("div", { class: "fila" },
      el("div", {}, el("b", {}, c.name.replace(" (demo)", "")), el("div", { class: "suave" }, `a ${km(c.distance_m)} km${c.distance_m != null && c.distance_m > 5000 ? " · fuera de tu radio de 5 km" : ""}`)),
      el("span", { class: `chip ${c.status === "listo" ? "exito" : "alerta"}` }, c.status === "listo" ? "Pedido listo" : "Preparando"))))];
}

const marcasComercios = new Map();   // id del comercio → marcador en el mapa
function pintarComercios(lista) {
  for (const c of lista) {
    let m = marcasComercios.get(c.merchant_id);
    if (!m) { m = ponerComercio(mapa, [c.lon, c.lat], c.name.replace(" (demo)", "")); marcasComercios.set(c.merchant_id, m); }
    const e = m.getElement();
    e.classList.toggle("con-pedido", true);
    e.classList.toggle("pedido-listo", c.status === "listo");
  }
  for (const [id, m] of marcasComercios) if (!lista.some((c) => c.merchant_id === id)) { m.remove(); marcasComercios.delete(id); }
}

function panelDelPedido() {
  const dist = distanciaAlObjetivo();
  const cerca = dist != null && dist <= RADIO_LLEGADA_M;
  const donde = activo.status === "asignado" ? "del comercio" : "del cliente";
  const consejo = activo.status === "en_comercio" ? "Ya estás en el comercio: cuando te entreguen los productos, tocá «Retiré el pedido»."
    : dist == null ? "Esperando tu ubicación…"
    : cerca ? "¡Ya llegaste! Podés marcar el paso."
    : `Estás a ${redondear10(dist)} m ${donde}. Tenés que estar a menos de ${RADIO_LLEGADA_M} m.`;
  const titulo = { asignado: "1. Andá al comercio", en_comercio: "2. Retirá el pedido", en_camino: "3. Llevalo al cliente" }[activo.status];
  const boton = {
    asignado: el("button", { class: "btn ancho", type: "button", disabled: !cerca, onclick: () => avanzar("arrived") }, "Llegué al comercio"),
    en_comercio: el("button", { class: "btn ancho", type: "button", onclick: () => avanzar("picked-up") }, "Retiré el pedido"),
    en_camino: el("button", { class: "btn ancho", type: "button", disabled: !cerca, onclick: () => avanzar("delivered") }, "Entregué el pedido"),
  }[activo.status];
  const conducir = activo.status === "en_comercio" ? null : el("button", { class: "btn secundario ancho", type: "button", onclick: alternarPiloto },
    pilotoActivo ? "Detener la moto" : `Conducir hacia el ${activo.status === "asignado" ? "comercio" : "cliente"}`);
  return el("div", { class: "tarjeta apilado" },
    el("div", { class: "fila" }, el("b", {}, titulo), chipEstado(activo.status)),
    el("p", { class: `suave${cerca ? "" : ""}`, style: "margin:0" + (cerca ? ";color:var(--exito);font-weight:700" : "") }, consejo),
    el("div", { class: "fila" }, el("span", { class: "suave" }, "Tu ganancia por este pedido"), el("b", { class: "dinero" }, dinero(activo.courier_pay_cents ?? 0))),
    boton, conducir);
}

function pintarPanel() {
  const hijos = [];
  hijos.push(el("div", { class: "tarjeta fila" },
    el("div", { class: "interruptor" }, el("b", {}, estado === "offline" ? "Desconectado" : estado === "busy" ? "Con un pedido" : "Disponible"),
      estado === "busy" ? null : el("span", { class: `chip ${estado === "available" ? "exito" : ""}` }, estado === "available" ? "Recibiendo ofertas" : "Sin ofertas")),
    estado === "busy" ? null : el("button", { class: "btn chico", type: "button", disabled: estado === "offline" && !miPos, onclick: () => cambiarEstado(estado === "available" ? "offline" : "available") },
      estado === "available" ? "Desconectarme" : "Ponerme disponible")));
  if (!miPos) hijos.push(el("div", { class: "vacio" }, "1. Tocá el mapa para indicar dónde estás. 2. Ponete disponible. 3. Esperá: cuando un comercio marque un pedido como listo, te llega la oferta."));
  else if (estado === "offline") hijos.push(el("div", { class: "vacio" }, "Ya estás en el mapa. Ahora tocá «Ponerme disponible» para recibir ofertas."));

  if (activo) {
    hijos.push(panelDelPedido());
  } else if (estado === "available") {
    if (!ofertas.length) hijos.push(el("div", { class: "vacio" }, el("p", { style: "margin:0 0 6px" }, "Esperando pedidos a menos de 5 km del comercio…"),
      el("p", { class: "suave", style: "margin:0;font-size:13px" }, "La oferta llega cuando el comercio marca el pedido como listo, y solo si estás a menos de 5 km de él.")));
    hijos.push(...tarjetasComercios());
    for (const o of ofertas) {
      const falta = segundosHasta(o.expires_at);
      const km = (m) => (m == null ? "?" : (m / 1000).toFixed(1).replace(".", ","));
      hijos.push(el("div", { class: "tarjeta apilado" },
        el("div", { class: "fila" }, el("div", {}, el("b", {}, o.merchant_name), el("div", { class: "suave" }, o.merchant_address)), el("div", { class: "cuenta", "aria-label": `${falta} segundos para responder` }, `${falta}s`)),
        el("div", { class: "suave" }, `Entrega en: ${o.delivery_address}`),
        el("div", { class: "fila" }, el("span", { class: "suave" }, `Hasta el comercio ${km(o.pickup_m)} km + entrega ${km(o.delivery_m)} km`), el("b", { class: "dinero" }, dinero(o.pay_cents))),
        el("div", { class: "fila" }, el("button", { class: "btn", style: "flex:1", type: "button", onclick: () => responder(o, true) }, `Aceptar · ganás ${dinero(o.pay_cents)}`),
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
  pintarPanel();
}
function nuevaPosicion(p) {   // la moto se movió (la llevé yo o el piloto automático)
  if (datosPedido) datosPedido = { ...datosPedido, courier: { lat: p.lat, lon: p.lon } };
  if (p.route) dibujarRuta(mapa, p.route);
  miPos = [p.lon, p.lat];
  if (miMarcador) moverSuave(miMarcador, miPos, 700); else miMarcador = ponerRepartidor(mapa, miPos, "Yo");
  pintarPanel();
}
function limpiarPedido() {
  cerrarStream?.(); cerrarStream = null; pedidoAbierto = null; datosPedido = null; mapa._encuadradoPedido = false; pilotoActivo = false;
  for (const k of Object.keys(marcasPedido)) { marcasPedido[k]?.remove(); marcasPedido[k] = null; }
  if (mapa.getLayer("ruta")) { mapa.removeLayer("ruta"); mapa.removeLayer("ruta-borde"); mapa.removeSource("ruta"); }
}

let ocupadoActualizando = false;
async function actualizar() {
  if (ocupadoActualizando) return;
  ocupadoActualizando = true;
  try {
    const [st, of, pedidos, w, prep] = await Promise.all([api("/courier/status"), api("/courier/offers"), api("/orders"), api("/wallet"), api("/courier/preparing")]);
    estado = st.status; ofertas = of;
    const hoyListos = new Set(prep.filter((c) => c.status === "listo").map((c) => c.merchant_id));
    if (yaListos) for (const c of prep) if (hoyListos.has(c.merchant_id) && !yaListos.has(c.merchant_id)) toast(`¡${c.name.replace(" (demo)", "")} tiene un pedido listo para retirar!`, "ok");
    yaListos = hoyListos;
    ganado.textContent = `Ganado hoy: ${dinero(w.today_cents)}`;
    if (!miPos && st.lat != null) {   // primera vez: dibujo mi moto donde el servidor dice que estoy
      miPos = [st.lon, st.lat];
      miMarcador = ponerRepartidor(mapa, miPos, "Yo");
      mapa.jumpTo({ center: miPos, zoom: 14.2 });
    }
    activo = pedidos.find((p) => ["asignado", "en_comercio", "en_camino"].includes(p.status)) ?? null;
    miMarcador?.getElement().classList.toggle("ocupado", estado === "busy");
    if (activo && pedidoAbierto !== activo.id) {
      limpiarPedido(); pedidoAbierto = activo.id;
      cerrarStream = suscribir(`/orders/${activo.id}/live`, { estado: mostrarPedido, posicion: nuevaPosicion });
    }
    if (!activo && pedidoAbierto) limpiarPedido();
    if (datosPedido && activo && datosPedido.status !== activo.status) datosPedido = { ...datosPedido, status: activo.status };
    ultimoActivo = activo;
    preparando = activo ? [] : prep;   // con un pedido en curso, el mapa muestra solo ese recorrido
    pintarComercios(preparando);
    pintarPanel();
  } catch (e) { if (e.estado !== 401) toast(e.message, "error"); }
  ocupadoActualizando = false;
}

await actualizar();
setInterval(actualizar, 2000);
setInterval(() => { if (ofertas.length && !activo) pintarPanel(); }, 1000);   // la cuenta regresiva baja cada segundo
