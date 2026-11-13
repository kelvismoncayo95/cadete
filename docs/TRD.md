# TRD · Diseño técnico

Cadete es un monolito modular en FastAPI con PostgreSQL y PostGIS, Redis para posiciones y eventos, un trabajador para el despacho, y un mapa propio de Montevideo servido como un archivo estático.

## 1. Stack y por qué

| Pieza | Elección | Motivo |
|---|---|---|
| Lenguaje | Python 3.12 | el que ya usás |
| API | FastAPI | validación, Swagger y SSE |
| Base de datos | PostgreSQL 17 + PostGIS | transacciones, restricciones y consultas geográficas |
| Acceso a datos | SQLAlchemy 2 + Alembic (+ GeoAlchemy2 ⚠) | migraciones versionadas |
| Redis | Redis | posiciones actuales, canales de eventos y límites de uso |
| Segundo plano | cola simple (RQ o Arq ⚠) | despacho, reintentos y reinicio nocturno |
| Tiempo real | SSE (Server-Sent Events) | el servidor empuja datos al cliente, con reconexión incluida |
| Mapa | MapLibre GL JS + archivo PMTiles propio | mapa de código abierto con estilo propio |
| Rutas | OSRM (perfil auto, algoritmo MLD) | rutas reales por calles, rápido y liviano |
| Direcciones | geocodificador propio: tablas `geo_calles` y `geo_direcciones` (OSM) + `pg_trgm` | buscar direcciones escritas sin servicios externos (311.134 puertas, 6.068 calles) |
| Pruebas | pytest | incluye concurrencia y consultas geográficas |
| Empaquetado | Docker Compose | api, worker, db, redis y simulador |
| Integración continua | GitHub Actions | tests y gitleaks en cada commit |
| Demo permanente | servicio barato (Render ⚠) | estable y casi gratis, como minipay |
| Nube como ejercicio | AWS + Terraform ⚠ | se levanta, se prueba, se documenta y se destruye |
| Observabilidad | logs en JSON y /metrics ⚠ | ver si el sistema está sano |

## 2. Arquitectura

```
Navegador (cliente, comercio, repartidor, admin)
    │  HTTP y SSE
    ▼
API (FastAPI): pedidos, catálogo, despacho, seguimiento
    │               │                 │
    ▼               ▼                 ▼
PostgreSQL        Redis           Trabajador
(+ PostGIS)   (posiciones,        (despacho, reintentos,
               eventos, límites)   reinicio nocturno)

Simulador de repartidores ──> API
Mapa: archivo PMTiles de Montevideo ──> navegador (MapLibre)
minipay (fase 6) ──> servicio aparte, hablan por HTTP
```

La base de datos es la fuente de verdad. Redis solo guarda lo que cambia rápido (la posición actual) y reparte eventos.

## 3. Capas del código

```
app/
  api/            # endpoints y SSE: reciben y responden
  services/       # reglas: pedidos, estados, despacho, seguimiento, demo
  models/         # tablas (SQLAlchemy)
  schemas/        # formatos de entrada y salida (Pydantic)
  core/           # configuración y seguridad
  worker/         # tareas en segundo plano
  simulator/      # mueve repartidores para la demo
alembic/          # migraciones
infra/            # Terraform (ejercicio de AWS)
map/              # extracto, estilo y scripts del mapa
tests/            # pytest
```

## 4. Decisiones técnicas

1. **Monolito modular, no microservicios.** Módulos: pedidos, catálogo, repartidores, despacho, seguimiento y demo. minipay queda aparte, como ejemplo de dos sistemas que se hablan.
2. **UUID en todo lo que expone la API.** Usuarios, comercios, productos, repartidores, pedidos y ofertas usan UUID, para que los IDs no se puedan adivinar. Las tablas internas (eventos, posiciones, auditoría) pueden usar números.
3. **PostGIS para ubicaciones.** Las posiciones se guardan como `geography(Point, 4326)`. El repartidor más cercano se busca con `ST_DWithin` más orden por distancia ⚠ (se verifica en la documentación de PostGIS).
4. **Máquina de estados en un solo lugar.** `services/order_state.py` define las transiciones válidas; cualquier otra devuelve 409. Cada cambio se guarda en `order_events`.
5. **Despacho sin dobles asignaciones.** Se eligen repartidores con `SELECT ... FOR UPDATE SKIP LOCKED`, así dos pedidos simultáneos nunca reciben el mismo. Un índice único parcial lo refuerza desde la base.
6. **Despacho al estar «listo».** Despachar antes, mientras el comercio prepara, queda como mejora futura.
7. **Ofertas con expiración.** Cada oferta tiene `expires_at`; el trabajador revisa las vencidas cada pocos segundos ⚠ y pasa al siguiente repartidor.
8. **Posición actual en Redis, histórico en PostgreSQL.** El repartidor manda su posición con un POST común cada 5 segundos. El histórico se conserva 7 días ⚠.
9. **Tiempo real con SSE.** Un canal por pedido. El cliente solo recibe, así que no hace falta WebSocket. Si se corta la conexión, el navegador reconecta solo y el cliente pide el estado con un GET: nunca se confía en haber recibido todos los eventos.
10. **Idempotencia al crear pedidos.** Cabecera `Idempotency-Key`, igual que en minipay.
11. **Rutas por calles (OSRM).** Un motor de rutas open source (OSRM, imagen oficial) con los datos de OpenStreetMap de Uruguay (Geofabrik, ODbL) calcula rutas, distancias y tiempos respetando sentidos únicos y giros prohibidos. Los datos se preparan una vez con `routing/preparar.sh` (extract, partition, customize; unos 90 s y 222 MB de RAM) y el servidor usa ~160 MB. El «más cercano» se elige con un prefiltro barato en PostGIS (los 8 más cercanos en línea recta) y el tiempo real por calle de esos 8 con la API `table`. Destinos y posiciones se validan con `nearest` (a ≤ 150 m de una calle). Si OSRM no responde, `ConRespaldo` usa línea recta y el sistema lo informa (`/admin/system`). Una sola configuración (perfil auto) para todos los repartidores.
12. **Permisos por rol, con 404 en lo ajeno.** Un cliente que pide el pedido de otro recibe 404, no 403.
13. **Simulador de repartidores.** Un proceso que mueve repartidores entre puntos de Montevideo y responde ofertas; sin él, la demo se vería vacía.
14. **Reinicio nocturno.** Una tarea programada vacía y vuelve a sembrar la base de la demo.
15. **Límites de uso con Redis.** Por IP y por usuario, en login, creación de pedidos y respuestas a ofertas.

## 5. El mapa propio

**Objetivo:** un mapa de Montevideo con aspecto moderno y propio, sin depender de un proveedor.

**Restricción de hardware:** la PC tiene 3,8 GB de RAM. No se compilan teselas desde cero (Planetiler necesita mucha memoria). Se descarga un recorte ya armado.

1. **Datos:** Protomaps publica compilaciones del planeta a partir de OpenStreetMap en formato PMTiles ⚠ (se verifica su página y su licencia en el paso 11).
2. **Recorte:** con `pmtiles extract` se baja solo el rectángulo de Montevideo, sin descargar el planeta entero ⚠.
3. **Estilo:** se diseña en un editor visual (Maputnik, por ejemplo) con la paleta del documento de UX/UI. **Acá se invierte la semana:** el estilo es lo que evita el aspecto viejo.
4. **Dibujo:** MapLibre GL JS en el navegador, leyendo el archivo PMTiles.
5. **Tipografías e íconos:** propios del proyecto; las tipografías Noto de basemaps-assets sirven como base ⚠.
6. **Capa propia:** repartidores, comercios, destinos y rutas se dibujan encima como capas, con datos de la API en GeoJSON.
7. **Alojamiento:** en local, un servidor estático; en producción, el mismo archivo servido de forma estática ⚠.
8. **Licencia:** los datos son de OpenStreetMap (licencia ODbL): el mapa debe mostrar «© OpenStreetMap» siempre visible. Si se usan estilos o teselas de Protomaps, se cumplen sus condiciones de atribución ⚠.
9. **Tope de tiempo:** una semana. Si se pasa, se usa un estilo base y se sigue.

## 6. Nube ⚠

Todo lo de esta sección se verifica en la documentación oficial antes de crear recursos: los servicios, el nivel gratuito y los precios cambian.

**Demo permanente (barata y estable):** Render, como en minipay, o una sola máquina con `docker compose` ⚠. Se decide en el paso 14, y se comprueba que PostGIS esté disponible en la base elegida.

**AWS como ejercicio:** con Terraform se describe una infraestructura (contenedores, base gestionada con PostGIS, almacenamiento estático para el mapa), se levanta, se prueba, se documenta con capturas y se **destruye**. Reglas:
- La **alerta de gasto se activa antes de crear nada**, y todo recurso lleva etiqueta de proyecto.
- Cuidado con los recursos que cobran por existir aunque no se usen (por ejemplo, el NAT Gateway); se evitan o se destruyen el mismo día.
- Los secretos van en el servicio de secretos, nunca en el repositorio.
- Al terminar, se verifica en la consola que no queda nada encendido.

## 7. Seguridad

- Datos inventados siempre: comercios ficticios y nada de personas reales.
- Las contraseñas de demo son públicas, pero se guardan con hash.
- Permisos por rol, 404 en recursos ajenos y límites de uso en login, pedidos y ofertas.
- Sesiones con token de corta duración, y CORS limitado a los orígenes de la demo.
- Secretos en variables de entorno; gitleaks en CI.
- Las posiciones son simuladas: la demo no guarda ubicaciones de nadie.

## 8. Pruebas

- Base separada `cadete_test`; el conftest se niega a correr si el nombre no termina en `_test`.
- El primer test de cada paso se escribe antes del código.
- Estados: cada transición válida pasa, y las inválidas dan 409.
- Despacho: dos pedidos simultáneos y un solo repartidor, y uno solo lo recibe (el test se prueba rompiendo el código a propósito).
- Geografía: con repartidores en posiciones conocidas, siempre sale el más cercano y se respeta el radio.
- Ofertas: una oferta vencida pasa al siguiente repartidor.
- Permisos: cada rol solo ve lo suyo.
- Idempotencia: repetir la creación no duplica pedidos.
- Tiempo real: reconectar y recuperar el estado correcto.

## 9. Observabilidad

- Registros en JSON con un identificador por petición.
- `/health` y `/metrics` con contadores de pedidos por estado, ofertas, expiraciones y tiempos de despacho ⚠.

## 10. Entornos

- **Local:** `docker compose up` (api, worker, db, redis y simulador).
- **CI:** GitHub Actions con servicios PostgreSQL con PostGIS y Redis, y gitleaks.
- **Demo pública:** servicio barato (paso 14).
- **AWS:** solo como ejercicio temporal (paso 13).
