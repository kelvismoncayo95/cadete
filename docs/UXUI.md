# UX/UI · Pantallas, mapa y mensajes

Cadete se diseña primero para el celular: el cliente y el repartidor usan el teléfono, y el comercio y el administrador, la pantalla grande. El mapa es el protagonista y debe verse moderno, limpio y propio.

## 1. Estilo de la interfaz

- **Identidad propia, distinta de clínica y minipay:** acento naranja quemado (#C2410C en tema claro, #FB923C en oscuro), fondo casi blanco cálido (#FAF8F5) y texto gris oscuro (#1F2421) ⚠ (se ajustan mirando las pantallas reales).
- Tipografía **Manrope** ⚠, esquinas de 16 px e iconos de línea.
- Un aviso fijo y discreto: «Datos inventados · demo pública · se reinicia cada noche».
- Contraste mínimo 4.5:1, botones de al menos 44 px y foco visible.

## 2. Pantallas por rol

| Rol | Pantalla | Qué muestra |
|---|---|---|
| Todos | Entrada | usuarios de demo por rol con «Entrar como…»; también usuario y contraseña. Sin registro |
| Cliente | Comercios | lista y mapa con los comercios abiertos |
| Cliente | Pedido | productos, cantidades, destino en el mapa, resumen y «Confirmar» |
| Cliente | Seguimiento | mapa grande con el repartidor moviéndose, estado y tiempo estimado |
| Comercio | Tablero | columnas Recibido, Preparando y Listo, con botones de acción |
| Repartidor | Ofertas | tarjeta con comercio, destino, distancia y cuenta regresiva de 30 segundos |
| Repartidor | Entrega | ruta en el mapa y botones «Retiré el pedido» y «Entregado» |
| Administrador | Mapa en vivo | todos los repartidores y pedidos activos |
| Administrador | Estado | salud del sistema |

## 3. Diseño del mapa

**Por qué se ven viejos los mapas gratuitos:** demasiadas etiquetas, colores saturados, calles gruesas y sin jerarquía, e íconos de otra época. El objetivo es lo contrario: calma, jerarquía y poco ruido.

**Principios**
1. **Menos es más:** pocas etiquetas, solo barrios, avenidas principales y la rambla. Nada de iconos de comercios por todos lados.
2. **Paleta suave:** tierra casi blanca, agua con un azul apagado y parques con un verde muy tenue.
3. **Calles finas y jerarquizadas:** las avenidas más gruesas que las calles, en blanco sobre un fondo gris claro.
4. **Tu capa destaca:** lo único con color fuerte son los repartidores, el destino y la ruta, en el naranja de la marca.
5. **Movimiento suave:** el repartidor se desliza entre posiciones con una transición, no salta.
6. **Dos temas:** claro y oscuro.

**Paleta propuesta ⚠ (se ajusta mirando el mapa real)**

| Elemento | Tema claro | Tema oscuro |
|---|---|---|
| Tierra | #F4F3F0 | #1A1D21 |
| Agua | #CFE0EA | #0F2733 |
| Parques | #DFE9D8 | #1E2D27 |
| Edificios | #EAE8E4 | #22262B |
| Calles | #FFFFFF con borde #DAD8D3 | #2C3138 |
| Avenidas | #FFFFFF, más gruesas | #383F48 |
| Etiquetas | #55595C con halo blanco | #B2B8BD con halo oscuro |
| Ruta | #C2410C, 5 px con borde blanco | #FB923C |

**Marcadores**
- Repartidor: círculo naranja con una moto de línea, y una pequeña flecha de dirección.
- Comercio: un pin cuadrado con el ícono de la categoría.
- Destino: un pin oscuro con una casa.
- Cada marcador tiene una etiqueta de texto, para no depender solo del color.

**Detalles**
- La atribución «© OpenStreetMap» siempre visible, pero discreta, en una esquina.
- En el celular, el mapa ocupa casi toda la pantalla y las acciones van en una hoja inferior.

## 4. Pantalla «Seguimiento», paso a paso

1. Mapa a pantalla casi completa, con la ruta y el repartidor.
2. Una hoja inferior con el estado en grande: «Tu pedido va en camino».
3. Una línea de tiempo corta: Recibido → Preparando → Listo → En camino → Entregado, con el paso actual resaltado.
4. Tiempo estimado: «Llega en unos 12 minutos». Es una estimación y se dice así.
5. Un botón «Cancelar pedido» visible solo mientras se puede cancelar.

## 5. Estados

| Situación | Cómo se ve |
|---|---|
| Cargando | esqueleto gris, nunca una pantalla en blanco |
| Sin repartidores todavía | «Estamos buscando un repartidor para tu pedido» con una animación suave |
| Conexión en vivo caída | aviso discreto «Reconectando…»; al volver, el mapa se corrige solo |
| Pedido entregado | tarjeta con el resumen |
| Error | mensaje con el motivo y un botón «Reintentar» |
| Lista vacía | mensaje útil: «No hay pedidos todavía. Probá «Simular un pedido»» |
| Demo reiniciada | aviso al entrar: «Los datos se restauraron esta noche» |

## 6. Mensajes

Siempre en español, claros, y dicen qué pasó y qué hacer:

- «Por ahora solo entregamos en Montevideo. Marcá un destino dentro de la zona.»
- «Tu pedido ya está en preparación y no se puede cancelar.»
- «Estamos buscando un repartidor. Te avisamos apenas haya uno.»
- «No respondiste a tiempo: la oferta pasó a otro repartidor.»

## 7. Accesibilidad y móvil

- Los estados se indican con texto además del color.
- Cada acción importante pide confirmación y anuncia su resultado en pantalla.
- Se comprueba en iPhone y en escritorio antes de dar por terminada cada pantalla.
- Se respeta la preferencia de «reducir movimiento» del sistema: sin animaciones fuertes.
