# App Flow · Cómo se mueve cada usuario

El camino principal es: el cliente pide, el comercio prepara, el sistema asigna a un repartidor, el repartidor entrega y el cliente lo ve en el mapa. Todo lo demás son casos alternos con un mensaje claro.

## 1. Entrar

1. El visitante abre la pantalla de entrada. Ve la lista de usuarios de demo, agrupados por rol, y el aviso «Datos inventados».
2. Toca «Entrar como Ana» (o escribe usuario y contraseña).
3. El sistema devuelve un token y lleva a la pantalla de su rol.

No hay pantalla de registro.

## 2. Cliente: hacer un pedido

1. Ve los comercios abiertos en una lista y en el mapa.
2. Elige uno y arma su pedido con los productos.
3. Escribe o marca el destino en el mapa, dentro de Montevideo.
4. Ve el resumen: productos, envío de $60 y total.
5. Toca «Confirmar». La app manda la petición con una clave de idempotencia.
6. El sistema crea el pedido en estado «recibido» y avisa al comercio.

## 3. Comercio: preparar

1. El tablero muestra el pedido nuevo en la columna «Recibido».
2. El comercio lo acepta («aceptado») o lo rechaza («rechazado», con un motivo).
3. Lo marca «preparando» y, cuando termina, «listo».
4. Al pasar a «listo», el sistema inicia la búsqueda del repartidor.

## 4. Despacho

1. El trabajador busca repartidores disponibles dentro del radio de 5 km, del más cercano al más lejano.
2. Bloquea al elegido, para que ningún otro pedido lo tome, y le manda una oferta con 30 segundos de plazo.
3. Si el repartidor acepta, el pedido pasa a «asignado».
4. Si rechaza o no responde, la oferta queda «expirada» o «rechazada» y se ofrece al siguiente (hasta 5 intentos).
5. Si no hay repartidores, el pedido queda «listo» y se reintenta cada 30 segundos. A los 10 minutos se avisa al comercio.

## 5. Repartidor: entregar

1. Recibe la oferta con el comercio, el destino, la distancia y la ganancia estimada. Toca «Aceptar» o «Rechazar».
2. Ve la ruta al comercio. Al llegar y retirar, toca «Retiré el pedido»; el estado pasa a «en camino».
3. Su posición se envía por POST cada 5 segundos mientras va en camino.
4. Al entregar, toca «Entregado»; el estado pasa a «entregado» y queda libre.

## 6. Cliente: seguimiento en vivo

1. La pantalla de seguimiento muestra el mapa, el repartidor moviéndose, el estado y el tiempo estimado.
2. Los cambios llegan por SSE.
3. Si se corta la conexión, el navegador reconecta solo, la app pide el estado actual con un GET y el mapa vuelve a ser correcto.
4. El cliente puede cancelar hasta «preparando».

## 7. Reinicio nocturno y simulador

1. El simulador mueve a los repartidores y responde ofertas, para que el mapa tenga vida.
2. A las 03:00 ⚠, una tarea vacía la base de la demo y la vuelve a sembrar.

## 8. Casos alternos

| Situación | Qué responde el sistema |
|---|---|
| Usuario o contraseña incorrectos | 401 «Usuario o contraseña incorrectos» |
| Muchos intentos seguidos | 429 «Demasiados intentos. Esperá un momento» |
| Carrito vacío | 422 «Elegí al menos un producto» |
| Cantidad fuera de rango | 422 «Podés pedir entre 1 y 20 unidades de cada producto» |
| Destino fuera de Montevideo | 422 «Por ahora solo entregamos en Montevideo» |
| Comercio cerrado | 409 «Este comercio está cerrado ahora» |
| Producto no disponible | 409 con el nombre del producto |
| Misma clave, mismo cuerpo | devuelve el pedido original, sin crear otro |
| Misma clave, otro cuerpo | 422 «Esa clave ya se usó con otro pedido» |
| Cancelar después de «preparando» | 409 «Tu pedido ya está en preparación y no se puede cancelar» |
| Cambio de estado inválido | 409 con el estado actual |
| Pedido de otra persona | 404 «No encontramos ese pedido» |
| Pedido sin repartidor disponible | queda «listo»; reintento cada 30 s; aviso al comercio a los 10 min |
| El repartidor no responde en 30 s | la oferta expira y pasa al siguiente |
| Dos pedidos y un repartidor | uno solo lo recibe; el otro sigue buscando |
| Se corta la conexión en vivo | el navegador reconecta y la app recupera el estado con un GET |
| Sesión vencida | 401 «Tu sesión venció» |
| Error interno | 500 «Algo falló de nuestro lado»; nada queda a medias |

## 9. Estados del pedido

recibido → aceptado → preparando → listo → asignado → **en_comercio** → en_camino → entregado

Ramas: recibido → rechazado (por el comercio) · recibido, aceptado o preparando → cancelado (por el cliente)

| Estado de la oferta | Significado |
|---|---|
| pendiente | esperando respuesta del repartidor |
| aceptada | el repartidor la tomó |
| rechazada | el repartidor la rechazó |
| expirada | pasaron los 30 segundos |

## 10. Endpoints (borrador ⚠)

Los identificadores `{id}` son UUID.

| Método y ruta | Para qué |
|---|---|
| POST /auth/login | entrar |
| GET /me | datos del usuario |
| GET /merchants | comercios abiertos |
| GET /merchants/{id}/products | productos de un comercio |
| GET /geocode?q= | buscar una dirección escrita (hasta 5 puntos posibles; 30 búsquedas por minuto) |
| POST /orders | crear un pedido (con Idempotency-Key) |
| GET /orders y GET /orders/{id} | mis pedidos y su detalle |
| POST /orders/{id}/cancel | cancelar (cliente) |
| POST /merchant/orders/{id}/accept, reject, preparing, ready | acciones del comercio |
| GET /courier/offers | ofertas pendientes |
| POST /courier/offers/{id}/accept y reject | responder una oferta |
| POST /courier/orders/{id}/arrived, picked-up y delivered | llegada al comercio (≤ 25 m), retiro y entrega (≤ 25 m del cliente; cobra y paga) |
| POST /courier/autopilot | demo: la moto va sola por las calles hacia su próximo destino |
| GET /wallet | mi saldo, lo de hoy y mis movimientos |
| POST /courier/location | enviar mi posición |
| GET /orders/{id}/live | seguimiento en vivo (SSE) |
| GET /admin/live | mapa de administración (SSE) |
| POST /demo/simulate-order | crear un pedido de prueba (solo API; la web ya no tiene botón) |
| GET /courier/preparing | comercios con pedidos preparando/listos, con distancia al repartidor |
| GET /health y /metrics | estado del sistema |
