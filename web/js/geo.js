// Distancia en línea recta entre dos puntos (metros). Sirve para habilitar los botones del repartidor;
// el servidor vuelve a comprobarlo (los botones solo reflejan lo mismo).
export function distanciaM(lat1, lon1, lat2, lon2) {
  const rad = Math.PI / 180, R = 6371000;
  const a = Math.sin(((lat2 - lat1) * rad) / 2) ** 2
    + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(((lon2 - lon1) * rad) / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

export const RADIO_LLEGADA_M = 150;   // igual que RADIO_LLEGADA_M del servidor (app/core/config.py)
export const redondear10 = (m) => Math.round(m / 10) * 10;
