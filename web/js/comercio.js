import { api, exigirRol } from "/js/api.js";
import { $, el, dinero, chipEstado, toast, barraSuperior } from "/js/ui.js";

const yo = exigirRol("merchant");
barraSuperior("Comercio");
const raiz = $("#raiz");
const detalles = new Map();      // id → pedido con líneas (se pide una sola vez)
let conocidos = null;            // ids ya vistos (null = primera carga: no avisar de «nuevos»)
let ocupado = false;

const COLUMNAS = [
  ["Nuevos", ["recibido"], "Cuando llegue un pedido, aparece acá. Probá «Simular un pedido»."],
  ["En preparación", ["aceptado", "preparando"], "Los pedidos que aceptes se preparan acá."],
  ["Listos", ["listo", "asignado", "en_camino"], "Los que están esperando o ya tienen repartidor."],
];

const hace = (iso) => {
  const min = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  return min < 1 ? "recién" : `hace ${min} min`;
};

async function simular(boton) {
  boton.disabled = true;
  try { await api("/demo/simulate-order", { metodo: "POST" }); toast("Llegó un pedido de prueba: atendelo desde «Nuevos»", "ok"); await cargar(); }
  catch (e) { toast(e.message, "error"); }
  boton.disabled = false;
}

async function accion(id, nombre) {
  try { await api(`/merchant/orders/${id}/${nombre}`, { metodo: "POST" }); await cargar(); }
  catch (e) { toast(e.message, "error"); await cargar(); }
}

function tarjeta(p, alertas) {
  const d = detalles.get(p.id);
  const botones = {
    recibido: [el("button", { class: "btn chico", type: "button", onclick: () => accion(p.id, "accept") }, "Aceptar"),
               el("button", { class: "btn secundario chico", type: "button", onclick: () => confirm("¿Rechazar este pedido?") && accion(p.id, "reject") }, "Rechazar")],
    aceptado: [el("button", { class: "btn chico", type: "button", onclick: () => accion(p.id, "preparing") }, "Empezar a preparar")],
    preparando: [el("button", { class: "btn chico", type: "button", onclick: () => accion(p.id, "ready") }, "Marcar listo")],
  }[p.status] ?? [];
  return el("article", { class: "tarjeta apilado", "aria-label": `Pedido ${p.id.slice(0, 6)}` },
    el("div", { class: "fila" }, el("b", {}, `#${p.id.slice(0, 6).toUpperCase()}`), chipEstado(p.status)),
    el("div", { class: "suave" }, hace(p.created_at), d?.notes === "[simulado]" ? " · simulado" : ""),
    d ? el("div", {}, d.items.map((i) => el("div", {}, `${i.quantity} × ${i.name}`))) : el("div", { class: "esqueleto", style: "height:40px" }),
    el("div", { class: "fila" }, el("span", { class: "suave" }, "Total"), el("b", { class: "dinero" }, dinero(p.total_cents))),
    p.status === "listo" && alertas.has(p.id) ? el("div", { class: "banner-alerta", role: "alert" }, "Hace más de 10 minutos que no hay repartidor para este pedido.") : null,
    p.status === "listo" && !alertas.has(p.id) ? el("div", { class: "suave" }, "Buscando repartidor…") : null,
    p.status === "asignado" ? el("div", { class: "suave" }, "Un repartidor va a retirarlo.") : null,
    p.status === "en_camino" ? el("div", { class: "suave" }, "Ya lo retiraron: va en camino al cliente.") : null,
    botones.length ? el("div", { class: "fila", style: "justify-content:flex-start" }, botones) : null);
}

function pintar(pedidos, alertas) {
  const terminados = pedidos.filter((p) => ["entregado", "rechazado", "cancelado"].includes(p.status));
  raiz.replaceChildren(...[
    el("div", { class: "fila" }, el("div", {}, el("h1", {}, "Tablero de pedidos"), el("p", { class: "suave" }, yo.display_name)),
      el("div", { class: "fila" },
        el("button", { class: "btn chico", type: "button", onclick: (e) => simular(e.currentTarget) }, "Simular un pedido"),
        el("div", { class: "chip exito" }, `${terminados.filter((p) => p.status === "entregado").length} entregados`))),
    el("div", { class: "tablero" }, COLUMNAS.map(([titulo, estados, vacio]) => {
      const lista = pedidos.filter((p) => estados.includes(p.status));
      return el("section", { class: "columna", "aria-label": titulo },
        el("h2", {}, titulo, el("span", { class: "chip" }, lista.length)),
        lista.length ? el("div", { class: "apilado" }, lista.map((p) => tarjeta(p, alertas))) : el("div", { class: "vacio" }, vacio));
    })),
    terminados.length ? el("details", { style: "margin-top:20px" }, el("summary", { class: "suave" }, `Finalizados (${terminados.length})`),
      el("div", { class: "apilado", style: "margin-top:10px" }, terminados.slice(0, 10).map((p) =>
        el("div", { class: "tarjeta fila" }, el("span", {}, `#${p.id.slice(0, 6).toUpperCase()} · ${hace(p.created_at)}`), chipEstado(p.status))))) : null,
  ].filter(Boolean));
}

async function cargar() {
  if (ocupado) return;
  ocupado = true;
  try {
    const [pedidos, avisos] = await Promise.all([api("/orders"), api("/merchant/alerts")]);
    await Promise.all(pedidos.filter((p) => !detalles.has(p.id)).map(async (p) => detalles.set(p.id, await api(`/orders/${p.id}`))));
    const ids = new Set(pedidos.map((p) => p.id));
    if (conocidos) for (const id of ids) if (!conocidos.has(id)) toast("Llegó un pedido nuevo", "ok");
    conocidos = ids;
    pintar(pedidos, new Set(avisos.map((a) => a.order_id)));
  } catch (e) { if (e.estado !== 401) toast(e.message, "error"); }
  ocupado = false;
}

await cargar();
setInterval(cargar, 3000);   // el tablero se actualiza solo cada 3 segundos
