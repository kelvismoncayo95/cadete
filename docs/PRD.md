# PRD · Cadete

**Proyecto:** Cadete (plataforma de pedidos y reparto en Montevideo) · **Autor:** Kelvis Moncayo · **Fecha:** 12 de noviembre de 2026 · **Estado:** aprobado, versión 2 (con correcciones)

> Decisiones del autor: (1) el nombre es Cadete, la palabra rioplatense para «repartidor»; (2) todo ocurre en Montevideo, con datos inventados; (3) el mapa es propio: calles reales de OpenStreetMap con un estilo diseñado por el autor; (4) el compromiso son las fases 1 a 3; las fases 4 a 6 se deciden después; (5) como en minipay, no hay registro: la demo usa usuarios ya creados; (6) tiempo real con SSE; (7) identidad visual propia, distinta de clínica y minipay. Lo marcado con ⚠ está por confirmar.

## 1. Qué es

Cadete es una plataforma donde un cliente pide a un comercio, el comercio prepara el pedido, el sistema asigna al repartidor más cercano y el cliente sigue el recorrido en un mapa en vivo. Es una versión pequeña de las apps de reparto, hecha para aprender y mostrar cómo se construyen por dentro.

## 2. Para qué existe

Demostrar que sé construir un backend con varios actores, eventos en tiempo real y consultas geográficas, y que sé llevarlo a la nube con despliegue automático. El autor trabaja como repartidor, así que conoce el problema desde adentro.

## 3. Quién lo usa

| Rol | Quién es | Qué hace |
|---|---|---|
| Cliente | un visitante de la demo (usuario publicado, como Ana) | elige un comercio, hace un pedido y lo sigue en el mapa |
| Comercio | un comercio de demo | recibe pedidos, los acepta, los prepara y los marca como listos |
| Repartidor | un repartidor de demo (por ejemplo Luis) | recibe ofertas, las acepta, retira y entrega |
| Administrador | el autor | ve el mapa en vivo y el estado del sistema |

## 4. Cómo es la demo pública

1. Los usuarios ya existen y sus credenciales se publican en el README y en la pantalla de entrada. **La contraseña es única y pública a propósito**, porque solo protege datos inventados.
2. No hay pantalla de registro.
3. Un simulador mueve a los repartidores por Montevideo, y un botón «Simular un pedido» crea pedidos de prueba, para que el mapa siempre tenga vida.
4. Cada noche, a las 03:00 (hora de Montevideo) ⚠, la base de la demo se reinicia con los datos de ejemplo.
5. Un aviso fijo dice «Datos inventados · demo pública».
6. Límites de uso protegen la demo del abuso (ver TRD).

## 5. Fases

| Fase | Qué se construye | Se puede mostrar cuando… |
|---|---|---|
| 1 | Pedidos, comercios y repartidores, con estados, permisos, Docker, CI y tests | un pedido se crea y avanza hasta «entregado» |
| 2 | Despacho al repartidor más cercano, seguimiento en vivo y mapa propio | el pedido «se mueve» en el mapa |
| 3 | Demo pública barata y estable, más infraestructura en AWS con Terraform como ejercicio | la demo funciona desde Internet y un comando levanta la infraestructura en AWS |
| 4 | Analítica: almacén de datos y tablero | hay un tablero de tiempos de entrega y horas pico |
| 5 | Catálogo con IA y cola de revisión | se sube un menú en PDF o foto y aparecen los productos |
| 6 | Pagos con minipay | un pedido se paga de punta a punta |

**El compromiso son las fases 1 a 3.** Las fases 4 a 6 se deciden después, según cómo vayan las entrevistas.

## 6. Historias de usuario

**Cliente**
1. Quiero entrar con un usuario de demo con un solo toque.
2. Quiero ver los comercios abiertos y sus productos.
3. Quiero armar un pedido, ver el total con el envío y confirmarlo.
4. Quiero que, si toco «Confirmar» dos veces, se cree un solo pedido.
5. Quiero seguir mi pedido en el mapa y ver el tiempo estimado.
6. Quiero cancelar mi pedido mientras todavía no empezó a prepararse.

**Comercio**
7. Quiero ver los pedidos nuevos en un tablero por estados y aceptarlos o rechazarlos.
8. Quiero marcar un pedido como «preparando» y como «listo».
9. Quiero ver qué repartidor viene a retirarlo y cuánto falta.

**Repartidor**
10. Quiero recibir ofertas de pedidos cercanos y aceptarlas o rechazarlas en 30 segundos.
11. Quiero ver la ruta al comercio y al cliente, y marcar «retirado» y «entregado».

**Administrador**
12. Quiero ver en un mapa a todos los repartidores y pedidos activos.
13. Quiero saber si el sistema está sano.

## 7. Reglas de negocio

| Regla | Detalle |
|---|---|
| Zona | el comercio y el destino deben estar dentro de la zona de Montevideo; fuera de ella, el pedido se rechaza |
| Pedido | un solo comercio por pedido, al menos 1 producto y entre 1 y 20 unidades por producto |
| Precios | pesos de juguete, guardados en centavos; envío fijo de $60 (confirmado) |
| Cancelación | el cliente cancela hasta «preparando»; después, no |
| Búsqueda de repartidor | repartidores disponibles dentro de 5 km del comercio (confirmado); se elige al que **llega más rápido por las calles** |
| Rutas | por calles reales, respetando sentidos únicos y giros prohibidos (motor OSRM con datos de OpenStreetMap). Un destino o posición a más de 150 m de una calle (por ejemplo, en el agua) se rechaza. Si el motor de rutas no responde, se usa línea recta como respaldo y el panel del admin lo marca como «degradado» |
| Oferta | el repartidor tiene 30 segundos para responder (confirmado); si rechaza o no responde, pasa al siguiente |
| Despacho | empieza cuando el pedido está «listo». Despachar antes, mientras se prepara, queda como mejora futura |
| Intentos | hasta 5 ofertas por pedido |
| Sin repartidores | el pedido queda «listo» y se reintenta cada 30 segundos; a los 10 minutos se avisa al comercio |
| Un solo pedido por repartidor | un repartidor atiende un pedido a la vez |
| Posiciones | el repartidor en camino envía su posición cada 5 segundos, por POST |
| Repetición | crear un pedido con la misma clave de idempotencia lo crea una sola vez |
| Privacidad | cada rol ve solo lo suyo: el cliente, sus pedidos; el comercio, los suyos; el repartidor, los asignados |

## 8. Alcance

**Incluye (fases 1 a 3):** login con usuarios de demo, comercios y catálogo, pedidos con estados y permisos, despacho al más cercano, ofertas con expiración, seguimiento en vivo con SSE, mapa propio de Montevideo, simulador de repartidores, reinicio nocturno, tests, Docker Compose, CI, demo pública, ejercicio de AWS con Terraform y observabilidad básica.

**Fases 4 a 6 (después):** analítica, catálogo con IA y pagos con minipay.

**No incluye:** registro público, dinero real, datos reales de personas o comercios, app móvil nativa.

## 9. Criterios de éxito

- Un pedido recorre todos sus estados y cada cambio queda registrado.
- Dos pedidos simultáneos con un solo repartidor disponible: uno solo lo recibe (con test).
- La búsqueda del repartidor devuelve siempre al más cercano disponible (con test geográfico).
- Una oferta que expira pasa al siguiente repartidor.
- Un cliente nunca puede ver ni tocar el pedido de otro (404).
- El cliente ve moverse al repartidor en el mapa, y si se corta la conexión, al volver recupera el estado correcto.
- `docker compose up` levanta todo desde cero y los tests pasan en GitHub Actions.
- La demo funciona desde Internet, y la infraestructura de AWS se levanta y se destruye con comandos.

## 10. Riesgos

- **Alcance grande:** por eso el compromiso son las fases 1 a 3, y cada fase termina con una demo.
- **Costos en la nube:** AWS solo como ejercicio que se levanta y se destruye, con alerta de gasto activa antes de crear nada. La demo permanente va en un servicio barato.
- **Tiempo en el mapa:** tope de una semana; si se pasa, se usa un estilo base y se sigue.
- **Abuso de la demo pública:** límites de uso y reinicio nocturno.
- **Que parezca un servicio real:** aviso permanente, comercios con nombres inventados y sin marcas reales.

## 11. Preguntas abiertas

1. ¿Hora del reinicio nocturno? (propuesta: 03:00, hora de Montevideo)
2. ¿Dónde corre la demo permanente? (propuesta: Render, como minipay; se decide en el paso 14)
3. ¿Buscás trabajo remoto, en Uruguay o las dos cosas? (decisión personal del autor; orienta qué se enfatiza en el README)
