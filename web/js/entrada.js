import { api, sesion } from "/js/api.js";
import { $, el, aplicarTema, toast } from "/js/ui.js";

aplicarTema();
const DESTINO = { customer: "/cliente.html", merchant: "/comercio.html", courier: "/repartidor.html", admin: "/admin.html" };
const GRUPOS = [
  ["customer", "Cliente", "Hacé un pedido y seguilo en el mapa."],
  ["merchant", "Comercio", "Recibí pedidos y prepará los que llegan."],
  ["courier", "Repartidor", "Aceptá ofertas, retirá y entregá."],
  ["admin", "Administrador", "Mirá todo el sistema en un mapa en vivo."],
];

async function entrar(usuario, clave) {
  try {
    const t = await api("/auth/login", { metodo: "POST", cuerpo: { username: usuario, password: clave } });
    sesion.guardar({ token: t.access_token, role: t.role, username: usuario, display_name: usuario });
    const yo = await api("/me");
    sesion.guardar({ token: t.access_token, role: t.role, username: yo.username, display_name: yo.display_name });
    location.href = DESTINO[t.role];
  } catch (e) { toast(e.message, "error"); }
}

const s = sesion.leer();
if (s) $("#aviso-sesion").append(el("div", { class: "tarjeta fila", style: "margin:12px 0" },
  el("span", {}, `Seguís dentro como `, el("b", {}, s.display_name), "."),
  el("a", { class: "btn chico", href: DESTINO[s.role] }, "Volver")));
if (new URLSearchParams(location.search).has("vencida")) toast("Tu sesión venció. Entrá de nuevo.");

const datos = await api("/demo/users");
$("#clave-demo").textContent = datos.password;
$("#grupos").replaceChildren(...GRUPOS.map(([rol, titulo, texto]) => {
  const usuarios = datos.users.filter((u) => u.role === rol && !u.simulated);
  const simulados = datos.users.filter((u) => u.role === rol && u.simulated).map((u) => u.display_name);
  return el("section", {},
    el("h2", {}, titulo), el("p", { class: "suave", style: "margin:-6px 0 10px" }, texto),
    el("div", { class: "rejilla" }, usuarios.map((u) =>
      el("button", { class: "btn secundario ancho", type: "button", onclick: () => entrar(u.username, datos.password) },
        rol === "merchant" ? u.display_name : `Entrar como ${u.display_name}`))),
    simulados.length ? el("p", { class: "suave" }, `${simulados.join(", ")} los maneja el simulador de la demo.`) : null);
}));
$("#manual").addEventListener("submit", (e) => { e.preventDefault(); entrar($("#usuario").value.trim(), $("#clave").value); });
