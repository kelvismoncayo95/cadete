import { api, exigirRol, suscribir } from "/js/api.js";
import { $, el, dinero, chipEstado, ESTADOS, PASOS, toast, barraSuperior, temaActual } from "/js/ui.js";
import { crearMapa, encuadrar, ponerComercio, ponerDestino, ponerRepartidor, moverSuave, dibujarRuta } from "/js/mapa.js";

exigirRol("customer");
barraSuperior("Cliente");
const raiz = $("#raiz");
const ENVIO_CENTAVOS = 6000;   // informativo: el servidor calcula el total de verdad
let limpiar = () => {};         // cierra el mapa y el stream de la pantalla anterior

const RUTAS = [
  [/^#\/pedido\/(.+)$/, pantallaPedido, "comercios"],
  [/^#\/seguir\/(.+)$/, pantallaSeguir, "pedidos"],
  [/^#\/pedidos$/, pantallaPedidos, "pedidos"],
  [/.*/, pantallaComercios, "comercios"],
];

async function navegar() {
  limpiar(); limpiar = () => {};
  raiz.replaceChildren(el("div", { class: "esqueleto" }));
  raiz.className = "contenedor";
  for (const [patron, pantalla, seccion] of RUTAS) {
    const m = location.hash.match(patron);
    if (!m) continue;
    document.querySelectorAll("#nav a").forEach((a) => a.dataset.ruta === seccion ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
    $("#nav").style.display = pantalla === pantallaSeguir ? "none" : "";   // el seguimiento ocupa toda la pantalla
    try { await pantalla(...m.slice(1)); } catch (e) { raiz.replaceChildren(el("div", { class: "vacio" }, e.message || "No se pudo cargar.")); }
    return;
  }
}
addEventListener("hashchange", navegar);

const centroDe = (c) => [c.lon, c.lat];
const abrirMapa = async (contenedor, opciones) => {
  const mapa = await crearMapa(contenedor, { tema: temaActual(), ...opciones });
  const anterior = limpiar;
  limpiar = () => { anterior(); mapa.remove(); };
  return mapa;
};

// ---------------------------------------------------------------- Comercios
async function pantallaComercios() {
  const comercios = await api("/merchants");
  const caja = el("div", { class: "mapa-caja" }, el("div", { class: "mapa-interno", id: "mapa" }));
  raiz.replaceChildren(
    el("h1", {}, "¿Qué se te antoja?"),
    el("p", { class: "suave" }, "Comercios abiertos en Montevideo."),
    el("div", { class: "fila", style: "margin:12px 0" },
      el("span", { class: "suave" }, "¿Sin ganas de armar un pedido? Probá cómo funciona:"),
      el("button", { class: "btn secundario chico", type: "button", id: "simular" }, "Simular un pedido")),
    caja, el("h2", {}, `${comercios.length} comercios`),
    el("div", { class: "rejilla" }, comercios.map((c) =>
      el("a", { class: "tarjeta-link", href: `#/pedido/${c.id}` },
        el("div", { class: "tarjeta" }, el("b", {}, c.name), el("div", { class: "suave" }, `${c.category} · ${c.address}`))))));
  const mapa = await abrirMapa("mapa", { centro: [-56.17, -34.905], zoom: 12 });
  for (const c of comercios) {
    const m = ponerComercio(mapa, centroDe(c), c.name.replace(" (demo)", ""));
    m.getElement().style.cursor = "pointer";
    m.getElement().addEventListener("click", () => { location.hash = `#/pedido/${c.id}`; });
  }
  encuadrar(mapa, comercios.map(centroDe), { abajo: 30, arriba: 30, lados: 60 });
  $("#simular").addEventListener("click", async (e) => {
    e.target.disabled = true;
    try { const p = await api("/demo/simulate-order", { metodo: "POST" }); location.hash = `#/seguir/${p.id}`; }
    catch (err) { toast(err.message, "error"); e.target.disabled = false; }
  });
}

// ------------------------------------------------------------ Armar el pedido
async function pantallaPedido(merchantId) {
  const [comercios, productos] = await Promise.all([api("/merchants"), api(`/merchants/${merchantId}/products`)]);
  const comercio = comercios.find((c) => c.id === merchantId);
  if (!comercio) { raiz.replaceChildren(el("div", { class: "vacio" }, "Este comercio no está abierto ahora.")); return; }
  const cantidades = new Map();
  let destino = [comercio.lon + 0.004, comercio.lat + 0.006];
  let claveIdempotencia = null;   // la misma mientras no cambie el pedido: tocar «Confirmar» dos veces no crea dos pedidos
  const cambio = () => { claveIdempotencia = null; pintarResumen(); };

  const resumen = el("div", { class: "resumen" });
  const confirmar = el("button", { class: "btn ancho", type: "button" }, "Confirmar pedido");
  const direccion = el("input", { type: "text", id: "direccion", value: "Mi casa (dirección de prueba)", maxlength: "160" });
  direccion.addEventListener("input", () => { claveIdempotencia = null; });

  function pintarResumen() {
    const subtotal = productos.reduce((t, p) => t + p.price_cents * (cantidades.get(p.id) ?? 0), 0);
    const unidades = [...cantidades.values()].reduce((a, b) => a + b, 0);
    resumen.replaceChildren(
      el("div", { class: "fila" }, el("span", {}, "Productos"), el("span", { class: "dinero" }, dinero(subtotal))),
      el("div", { class: "fila" }, el("span", {}, "Envío"), el("span", { class: "dinero" }, dinero(ENVIO_CENTAVOS))),
      el("div", { class: "fila total" }, el("b", {}, "Total"), el("b", { class: "dinero" }, dinero(subtotal + (unidades ? ENVIO_CENTAVOS : 0)))));
    confirmar.disabled = unidades === 0;
    confirmar.textContent = unidades ? `Confirmar pedido · ${dinero(subtotal + ENVIO_CENTAVOS)}` : "Elegí al menos un producto";
  }

  const filas = productos.map((p) => {
    const salida = el("output", { "aria-live": "polite" }, "0");
    const poner = (delta) => {
      const n = Math.min(20, Math.max(0, (cantidades.get(p.id) ?? 0) + delta));
      n ? cantidades.set(p.id, n) : cantidades.delete(p.id);
      salida.textContent = n; cambio();
    };
    return el("div", { class: "producto" },
      el("div", {}, el("b", {}, p.name), el("div", { class: "suave dinero" }, dinero(p.price_cents))),
      el("div", { class: "stepper" },
        el("button", { type: "button", "aria-label": `Quitar ${p.name}`, onclick: () => poner(-1) }, "−"), salida,
        el("button", { type: "button", "aria-label": `Agregar ${p.name}`, onclick: () => poner(1) }, "+")));
  });

  raiz.replaceChildren(
    el("a", { href: "#/", class: "suave" }, "← Comercios"),
    el("h1", {}, comercio.name), el("p", { class: "suave" }, `${comercio.category} · ${comercio.address}`),
    el("div", { class: "tarjeta" }, filas),
    el("h2", {}, "¿Dónde te lo llevamos?"),
    el("p", { class: "suave" }, "Tocá el mapa para marcar el destino. Por ahora solo entregamos en Montevideo."),
    el("div", { class: "mapa-caja" }, el("div", { class: "mapa-interno", id: "mapa" })),
    el("label", { for: "direccion" }, "Dirección"), direccion,
    el("h2", {}, "Resumen"), el("div", { class: "tarjeta" }, resumen),
    el("div", { style: "margin-top:14px" }, confirmar));
  pintarResumen();

  const mapa = await abrirMapa("mapa", { centro: destino, zoom: 13.5 });
  ponerComercio(mapa, centroDe(comercio), comercio.name.replace(" (demo)", ""));
  const pin = ponerDestino(mapa, destino, "Entregar acá");
  mapa.on("click", (e) => { destino = [e.lngLat.lng, e.lngLat.lat]; pin.setLngLat(destino); cambio(); });
  encuadrar(mapa, [centroDe(comercio), destino], { abajo: 40, arriba: 40, lados: 70 });

  confirmar.addEventListener("click", async () => {
    confirmar.disabled = true;
    claveIdempotencia ??= crypto.randomUUID();
    try {
      const pedido = await api("/orders", { metodo: "POST", clave: claveIdempotencia, cuerpo: {
        merchant_id: merchantId, delivery_address: direccion.value.trim() || "Sin dirección",
        delivery_lat: destino[1], delivery_lon: destino[0],
        items: [...cantidades].map(([product_id, quantity]) => ({ product_id, quantity })),
      } });
      location.hash = `#/seguir/${pedido.id}`;
    } catch (e) { toast(e.message, "error"); pintarResumen(); }
  });
}

// ------------------------------------------------------------- Seguimiento
const MENSAJES = {
  recibido: "Esperando que el comercio acepte tu pedido.", aceptado: "El comercio aceptó tu pedido.",
  preparando: "Están preparando tu pedido.", listo: "Estamos buscando un repartidor para tu pedido.",
  asignado: "Un repartidor va al comercio a retirar tu pedido.", en_camino: "Tu pedido va en camino.",
  entregado: "¡Tu pedido fue entregado!", rechazado: "El comercio no pudo aceptar tu pedido.", cancelado: "Cancelaste este pedido.",
};
const PASO_DE = { recibido: 0, aceptado: 0, preparando: 1, listo: 2, asignado: 2, en_camino: 3, entregado: 4 };
const CANCELABLES = ["recibido", "aceptado", "preparando"];

async function pantallaSeguir(orderId) {
  const [pedido, comercios] = await Promise.all([api(`/orders/${orderId}`), api("/merchants")]);
  const nombre = comercios.find((c) => c.id === pedido.merchant_id)?.name ?? "el comercio";
  raiz.className = ""; raiz.replaceChildren(el("div", { class: "mapa-completo", id: "mapa" }));
  const hoja = el("section", { class: "hoja-fija", "aria-live": "polite" });
  document.body.append(hoja);
  const anterior = limpiar; limpiar = () => { anterior(); hoja.remove(); };

  const mapa = await abrirMapa("mapa", { centro: [-56.17, -34.905], zoom: 13 });
  let mComercio, mDestino, mRepartidor, cerrarStream;
  let conectado = true;
  const detalle = el("details", { class: "suave", style: "margin-top:8px" }, el("summary", {}, `Tu pedido a ${nombre}`),
    el("div", {}, pedido.items.map((i) => el("div", { class: "fila" }, el("span", {}, `${i.quantity} × ${i.name}`), el("span", { class: "dinero" }, dinero(i.unit_price_cents * i.quantity)))),
      el("div", { class: "fila" }, el("b", {}, "Total (con envío)"), el("b", { class: "dinero" }, dinero(pedido.total_cents)))));

  function pintarHoja(d) {
    const paso = PASO_DE[d.status];
    const cancelable = CANCELABLES.includes(d.status);
    hoja.replaceChildren(...[
      el("a", { href: "#/pedidos", class: "suave" }, "← Mis pedidos"),
      el("div", { class: "fila", style: "margin-top:6px" }, el("p", { class: "estado-grande" }, MENSAJES[d.status]), chipEstado(d.status)),
      ["rechazado", "cancelado"].includes(d.status) ? null : el("ol", { class: "linea-tiempo", "aria-label": "Progreso" },
        PASOS.map((p, i) => el("li", { class: i < paso ? "hecho" : i === paso ? "hecho actual" : "", "aria-current": i === paso ? "step" : null }, ESTADOS[p][0].replace(" · buscando repartidor", "")))),
      d.eta_min != null ? el("p", {}, "Llega en unos ", el("b", {}, `${d.eta_min} minuto${d.eta_min === 1 ? "" : "s"}`), el("span", { class: "suave" }, " (es una estimación)")) : null,
      !conectado ? el("p", { class: "chip alerta", role: "status" }, "Reconectando…") : null,
      detalle,
      cancelable ? el("button", { class: "btn peligro ancho", type: "button", style: "margin-top:10px", onclick: cancelar }, "Cancelar pedido") : null,
    ].filter(Boolean));
  }
  let ultimo;
  const repintar = () => ultimo && pintarHoja(ultimo);

  async function cancelar() {
    if (!confirm("¿Querés cancelar este pedido?")) return;
    try { await api(`/orders/${orderId}/cancel`, { metodo: "POST" }); toast("Pedido cancelado", "ok"); }
    catch (e) { toast(e.message, "error"); }
  }

  function aplicarEstado(d) {
    ultimo = d;
    const c = d.merchant, dst = d.destino, rep = d.courier;
    mComercio ??= ponerComercio(mapa, [c.lon, c.lat], nombre.replace(" (demo)", ""));
    mDestino ??= ponerDestino(mapa, [dst.lon, dst.lat], "Tu casa");
    if (rep) { if (!mRepartidor) mRepartidor = ponerRepartidor(mapa, [rep.lon, rep.lat], "Repartidor"); else moverSuave(mRepartidor, [rep.lon, rep.lat]); }
    const camino = d.status === "en_camino" && rep ? [[rep.lon, rep.lat], [dst.lon, dst.lat]]
      : d.status === "asignado" && rep ? [[rep.lon, rep.lat], [c.lon, c.lat], [dst.lon, dst.lat]] : [[c.lon, c.lat], [dst.lon, dst.lat]];
    const dibujar = () => dibujarRuta(mapa, camino);
    mapa.loaded() ? dibujar() : mapa.once("load", dibujar);
    if (!mapa._encuadrado) { encuadrar(mapa, [[c.lon, c.lat], [dst.lon, dst.lat], ...(rep ? [[rep.lon, rep.lat]] : [])], { abajo: 320, arriba: 90, lados: 60 }); mapa._encuadrado = true; }
    pintarHoja(d);
    if (["entregado", "rechazado", "cancelado"].includes(d.status)) cerrarStream?.();
  }
  function aplicarPosicion(d) {
    if (!mRepartidor) return;
    moverSuave(mRepartidor, [d.lon, d.lat]);
    if (ultimo) { ultimo = { ...ultimo, eta_min: d.eta_min, courier: { lat: d.lat, lon: d.lon } }; pintarHoja(ultimo); }
  }

  cerrarStream = suscribir(`/orders/${orderId}/live`, { estado: aplicarEstado, posicion: aplicarPosicion }, (ok) => { conectado = ok; repintar(); });
  const anterior2 = limpiar; limpiar = () => { anterior2(); cerrarStream?.(); };
}

// ------------------------------------------------------------ Mis pedidos
async function pantallaPedidos() {
  const [pedidos, comercios] = await Promise.all([api("/orders"), api("/merchants")]);
  const nombres = new Map(comercios.map((c) => [c.id, c.name]));
  raiz.replaceChildren(el("h1", {}, "Mis pedidos"),
    pedidos.length ? el("div", { class: "apilado" }, pedidos.map((p) =>
      el("a", { class: "tarjeta-link", href: `#/seguir/${p.id}` }, el("div", { class: "tarjeta" },
        el("div", { class: "fila" }, el("b", {}, nombres.get(p.merchant_id) ?? "Comercio"), chipEstado(p.status)),
        el("div", { class: "fila suave" }, el("span", {}, new Date(p.created_at).toLocaleString("es-UY", { dateStyle: "short", timeStyle: "short" })), el("span", { class: "dinero" }, dinero(p.total_cents)))))))
      : el("div", { class: "vacio" }, "Todavía no hiciste pedidos. Probá «Simular un pedido» en Comercios."));
}

navegar();
