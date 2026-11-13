// Utilidades de interfaz compartidas.
import { sesion } from "/js/api.js";

export const $ = (selector, raiz = document) => raiz.querySelector(selector);

/** Crea un elemento: el("div", {class: "tarjeta"}, "texto", otroElemento) */
export function el(etiqueta, atributos = {}, ...hijos) {
  const nodo = document.createElement(etiqueta);
  for (const [k, v] of Object.entries(atributos)) {
    if (v === false || v == null) continue;
    if (k.startsWith("on")) nodo.addEventListener(k.slice(2), v);
    else if (k === "class") nodo.className = v;
    else nodo.setAttribute(k, v === true ? "" : v);
  }
  for (const h of hijos.flat()) if (h != null && h !== false) nodo.append(h.nodeType ? h : document.createTextNode(h));
  return nodo;
}

/** 35000 centavos → "$ 350" */
export function dinero(centavos) {
  return "$ " + (centavos / 100).toLocaleString("es-UY", { maximumFractionDigits: 0 });
}

export const ESTADOS = {
  recibido: ["Recibido", "info"], aceptado: ["Aceptado", "alerta"], preparando: ["Preparando", "alerta"],
  listo: ["Listo · buscando repartidor", "info"], asignado: ["Repartidor asignado", "acento"], en_comercio: ["Retirando el pedido", "acento"],
  en_camino: ["En camino", "acento"], entregado: ["Entregado", "exito"], rechazado: ["Rechazado", "peligro"],
  cancelado: ["Cancelado", "peligro"],
};
export const chipEstado = (estado) => el("span", { class: `chip ${ESTADOS[estado]?.[1] ?? ""}` }, ESTADOS[estado]?.[0] ?? estado);
export const PASOS = ["recibido", "preparando", "listo", "en_camino", "entregado"];

export function toast(mensaje, tipo = "") {
  let caja = $(".toasts");
  if (!caja) { caja = el("div", { class: "toasts", "aria-live": "polite" }); document.body.append(caja); }
  const t = el("div", { class: `toast ${tipo}`, role: tipo === "error" ? "alert" : "status" }, mensaje);
  caja.append(t);
  setTimeout(() => t.remove(), tipo === "error" ? 6000 : 3500);
}

/** Tema del sistema (claro/oscuro) aplicado a toda la página. */
export function aplicarTema() {
  const consulta = matchMedia("(prefers-color-scheme: dark)");
  const poner = () => { document.documentElement.dataset.tema = consulta.matches ? "oscuro" : "claro"; };
  poner();
  consulta.addEventListener("change", poner);
}
export const temaActual = () => document.documentElement.dataset.tema ?? "claro";

/** Barra superior con la marca, el usuario y «Salir» + el aviso fijo de demo. */
export function barraSuperior(rol) {
  aplicarTema();
  const s = sesion.leer();
  const barra = el("header", { class: "barra" },
    el("a", { class: "marca", href: "/" }, "Cadete"),
    s ? el("div", { class: "usuario" }, el("b", {}, s.display_name), rol) : null,
    s ? el("button", { class: "btn secundario chico", type: "button", onclick: () => { sesion.borrar(); location.href = "/"; } }, "Salir") : null);
  document.body.prepend(barra);   // el aviso «Datos inventados» va fijo en el HTML de cada página
}

/** Cuenta atrás en segundos hasta una fecha ISO. */
export const segundosHasta = (iso) => Math.max(0, Math.round((new Date(iso) - Date.now()) / 1000));
