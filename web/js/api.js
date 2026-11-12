// Cliente de la API: guarda la sesión, manda el token y traduce los errores a mensajes claros.
const CLAVE = "cadete_sesion";

export const sesion = {
  leer() { try { return JSON.parse(localStorage.getItem(CLAVE)); } catch { return null; } },
  guardar(datos) { try { localStorage.setItem(CLAVE, JSON.stringify(datos)); } catch { /* modo privado: se pierde al cerrar */ } },
  borrar() { try { localStorage.removeItem(CLAVE); } catch { /* nada que borrar */ } },
};

export class ErrorApi extends Error {
  constructor(estado, mensaje, datos) { super(mensaje); this.estado = estado; this.datos = datos; }
}

function mensajeDe(estado, datos) {
  if (typeof datos?.detail === "string") return datos.detail;
  if (estado === 422) return "Revisá los datos: algo no está bien.";
  if (estado === 429) return "Demasiados intentos. Esperá un momento.";
  if (estado >= 500) return "Algo falló de nuestro lado. Probá de nuevo.";
  return "No se pudo completar la acción.";
}

export async function api(ruta, { metodo = "GET", cuerpo, clave } = {}) {
  const s = sesion.leer();
  const cabeceras = { Accept: "application/json" };
  if (cuerpo !== undefined) cabeceras["Content-Type"] = "application/json";
  if (s?.token) cabeceras.Authorization = `Bearer ${s.token}`;
  if (clave) cabeceras["Idempotency-Key"] = clave;
  let respuesta;
  try {
    respuesta = await fetch(ruta, { method: metodo, headers: cabeceras, body: cuerpo !== undefined ? JSON.stringify(cuerpo) : undefined });
  } catch {
    throw new ErrorApi(0, "No hay conexión con el servidor. Revisá tu internet.", null);
  }
  if (respuesta.status === 204) return null;
  const datos = await respuesta.json().catch(() => null);
  if (!respuesta.ok) {
    if (respuesta.status === 401 && s) { sesion.borrar(); location.href = "/?vencida=1"; }
    throw new ErrorApi(respuesta.status, mensajeDe(respuesta.status, datos), datos);
  }
  return datos;
}

/** Cada pantalla pide su rol: si no hay sesión o es de otro rol, vuelve a la entrada. */
export function exigirRol(...roles) {
  const s = sesion.leer();
  if (!s || !roles.includes(s.role)) { location.replace("/"); throw new Error("sin sesión"); }
  return s;
}

/** Stream en vivo (SSE). El navegador reconecta solo; cada vez que reconecta llega de nuevo la foto del estado. */
export function suscribir(ruta, eventos, alCambiarConexion) {
  const s = sesion.leer();
  const fuente = new EventSource(`${ruta}?token=${encodeURIComponent(s.token)}`);
  for (const [nombre, manejador] of Object.entries(eventos)) {
    fuente.addEventListener(nombre, (e) => manejador(JSON.parse(e.data)));
  }
  fuente.onopen = () => alCambiarConexion?.(true);
  fuente.onerror = () => alCambiarConexion?.(false);
  return () => fuente.close();
}
