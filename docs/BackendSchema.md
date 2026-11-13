# Backend Schema · Base de datos

Las ubicaciones usan PostGIS (`geography`), y el estado de cada pedido queda registrado en un historial. Los índices únicos parciales hacen cumplir, desde la base, que un repartidor no tome dos pedidos a la vez.

**Identificadores:** todo lo que la API expone usa UUID (`gen_random_uuid()`, incluido en PostgreSQL), para que no se puedan adivinar. Las tablas internas, que la API no expone, usan números autoincrementales.

## 1. Esquema (borrador ⚠)

```sql
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username      VARCHAR(30) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  display_name  VARCHAR(60) NOT NULL,
  role          VARCHAR(10) NOT NULL
                CHECK (role IN ('customer','merchant','courier','admin')),
  is_active     BOOLEAN NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE merchants (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL UNIQUE REFERENCES users(id),
  name       VARCHAR(80) NOT NULL,
  category   VARCHAR(30) NOT NULL,
  address    VARCHAR(160) NOT NULL,
  location   GEOGRAPHY(Point, 4326) NOT NULL,
  is_open    BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE products (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant_id  UUID NOT NULL REFERENCES merchants(id),
  name         VARCHAR(80) NOT NULL,
  description  VARCHAR(200),
  price_cents  BIGINT NOT NULL CHECK (price_cents > 0),
  is_available BOOLEAN NOT NULL DEFAULT true,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE couriers (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL UNIQUE REFERENCES users(id),
  vehicle       VARCHAR(10) NOT NULL CHECK (vehicle IN ('moto','bici')),
  status        VARCHAR(10) NOT NULL DEFAULT 'offline'
                CHECK (status IN ('offline','available','busy')),
  last_location GEOGRAPHY(Point, 4326),
  last_seen_at  TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE orders (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_user_id   UUID NOT NULL REFERENCES users(id),
  merchant_id        UUID NOT NULL REFERENCES merchants(id),
  courier_id         UUID REFERENCES couriers(id),
  status             VARCHAR(12) NOT NULL
                     CHECK (status IN ('recibido','aceptado','preparando','listo',
                                       'asignado','en_camino','entregado',
                                       'rechazado','cancelado')),
  delivery_address   VARCHAR(160) NOT NULL,
  delivery_location  GEOGRAPHY(Point, 4326) NOT NULL,
  subtotal_cents     BIGINT NOT NULL CHECK (subtotal_cents > 0),
  delivery_fee_cents BIGINT NOT NULL CHECK (delivery_fee_cents >= 0),
  total_cents        BIGINT NOT NULL CHECK (total_cents > 0),
  notes              VARCHAR(200),   -- marca de la demo: '[simulado]' o '[demo]'
  courier_pay_cents  BIGINT,         -- lo que cobra el repartidor: se fija al aceptar la oferta
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE order_items (
  id               BIGSERIAL PRIMARY KEY,
  order_id         UUID NOT NULL REFERENCES orders(id),
  product_id       UUID NOT NULL REFERENCES products(id),
  name_snapshot    VARCHAR(80) NOT NULL,
  unit_price_cents BIGINT NOT NULL CHECK (unit_price_cents > 0),
  quantity         INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 20)
);

CREATE TABLE order_events (
  id            BIGSERIAL PRIMARY KEY,
  order_id      UUID NOT NULL REFERENCES orders(id),
  from_status   VARCHAR(12),
  to_status     VARCHAR(12) NOT NULL,
  actor_user_id UUID REFERENCES users(id),
  detail        JSONB,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE dispatch_offers (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id     UUID NOT NULL REFERENCES orders(id),
  courier_id   UUID NOT NULL REFERENCES couriers(id),
  status       VARCHAR(10) NOT NULL
               CHECK (status IN ('pendiente','aceptada','rechazada','expirada')),
  distance_m   INTEGER,
  offered_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at   TIMESTAMPTZ NOT NULL,
  responded_at TIMESTAMPTZ
);

CREATE TABLE courier_positions (
  id          BIGSERIAL PRIMARY KEY,
  courier_id  UUID NOT NULL REFERENCES couriers(id),
  location    GEOGRAPHY(Point, 4326) NOT NULL,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE idempotency_keys (
  id              BIGSERIAL PRIMARY KEY,
  user_id         UUID NOT NULL REFERENCES users(id),
  key             VARCHAR(80) NOT NULL,
  request_hash    CHAR(64) NOT NULL,
  response_status INTEGER NOT NULL,
  response_body   JSONB NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, key)
);

-- Libro de movimientos (dinero de juguete). Cada pedido ENTREGADO deja 4 asientos que suman cero.
CREATE TABLE ledger_entries (
  id           BIGSERIAL PRIMARY KEY,
  order_id     UUID NOT NULL REFERENCES orders(id),
  user_id      UUID REFERENCES users(id),          -- vacío = la plataforma
  concept      VARCHAR(30) NOT NULL,               -- cobro_cliente, pago_comercio, pago_repartidor, plataforma
  amount_cents BIGINT NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (order_id, concept)                       -- no se cobra dos veces
);

-- Geocodificador propio (datos de OpenStreetMap, se cargan con geocoder/cargar.py). Requiere la extensión pg_trgm.
CREATE TABLE geo_calles (
  id     SERIAL PRIMARY KEY,
  nombre VARCHAR(160) NOT NULL,
  norm   VARCHAR(160) NOT NULL,                    -- nombre normalizado (minúsculas, sin tildes, abreviaturas expandidas)
  geom   geometry(MultiLineString, 4326) NOT NULL
);
CREATE TABLE geo_direcciones (
  id         BIGSERIAL PRIMARY KEY,
  calle_norm VARCHAR(160) NOT NULL,
  numero     INTEGER NOT NULL,
  geom       geometry(Point, 4326) NOT NULL
);

CREATE TABLE audit_log (
  id            BIGSERIAL PRIMARY KEY,
  actor_user_id UUID REFERENCES users(id),
  action        VARCHAR(50) NOT NULL,
  entity        VARCHAR(30) NOT NULL,
  entity_id     VARCHAR(60),
  detail        JSONB,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_merchants_location   ON merchants USING GIST (location);
CREATE INDEX ix_couriers_location    ON couriers  USING GIST (last_location);
CREATE INDEX ix_orders_status        ON orders (status, created_at);
CREATE INDEX ix_orders_customer      ON orders (customer_user_id, created_at);
CREATE INDEX ix_orders_merchant      ON orders (merchant_id, status);
CREATE INDEX ix_events_order         ON order_events (order_id, created_at);
CREATE INDEX ix_positions_courier    ON courier_positions (courier_id, recorded_at);
CREATE INDEX ix_offers_order         ON dispatch_offers (order_id, offered_at);
CREATE INDEX ix_audit_created        ON audit_log (created_at);
CREATE INDEX ix_ledger_user          ON ledger_entries (user_id, created_at);
CREATE INDEX ix_geo_calles_geom      ON geo_calles USING GIST (geom);
CREATE INDEX ix_geo_calles_norm_trgm ON geo_calles USING GIN (norm gin_trgm_ops);
CREATE INDEX ix_geo_direcciones_calle_numero ON geo_direcciones (calle_norm, numero);

-- Una sola oferta pendiente por pedido y por repartidor
CREATE UNIQUE INDEX ux_offer_pending_order
  ON dispatch_offers (order_id)   WHERE status = 'pendiente';
CREATE UNIQUE INDEX ux_offer_pending_courier
  ON dispatch_offers (courier_id) WHERE status = 'pendiente';

-- Un repartidor no puede tener dos pedidos activos
CREATE UNIQUE INDEX ux_courier_active_order
  ON orders (courier_id) WHERE status IN ('asignado','en_comercio','en_camino');
```

## 2. Consulta clave: el repartidor más cercano

Se buscan repartidores con `status = 'available'` dentro del radio del comercio, ordenados por distancia, y se bloquea al elegido para que ningún otro pedido lo tome:

```sql
SELECT c.id
FROM couriers c
JOIN merchants m ON m.id = :merchant_id
WHERE c.status = 'available'
  AND ST_DWithin(c.last_location, m.location, 5000)
ORDER BY ST_Distance(c.last_location, m.location)
LIMIT 1
FOR UPDATE OF c SKIP LOCKED;
```

Es un borrador ⚠: se verifica en el paso 8 con la documentación de PostGIS, y se reemplaza por el operador de vecino más cercano si conviene.

## 3. Reglas que la base no puede escribir sola

Se comprueban en el código y en los tests:

1. Las transiciones de estado válidas (por ejemplo, de «recibido» a «aceptado», nunca a «entregado»).
2. `total_cents = subtotal_cents + delivery_fee_cents`, y `subtotal_cents` es la suma de las líneas.
3. Cada cambio de estado deja una fila en `order_events`.
4. Cuando se acepta una oferta, el pedido, el repartidor y la oferta cambian en la misma transacción.
5. El destino y el comercio están dentro de la zona de Montevideo ⚠.

## 4. Relaciones

- users 1 — 0..1 merchants o couriers (según el rol).
- merchants 1 — N products.
- orders N — 1 merchants, N — 1 users (cliente) y 0..1 — 1 couriers.
- orders 1 — N order_items y 1 — N order_events.
- orders 1 — N dispatch_offers.
- couriers 1 — N courier_positions.

## 5. Datos de demo (semilla)

| Tipo | Cuentas | Notas |
|---|---|---|
| Clientes | ana, pedro | usuarios de demo |
| Comercios | 4 o 5 comercios con nombres inventados y «(demo)» | repartidos por barrios de Montevideo (Pocitos, Ciudad Vieja, Cordón, Punta Carretas, Parque Rodó) |
| Repartidores | luis, marta, diego | moto o bici, con posiciones iniciales de ejemplo |
| Administrador | admin | solo para el autor |

Las coordenadas exactas se definen en el paso 7, sobre el mapa. La contraseña de demo es única y pública (se define en el paso 5; no reutilizar contraseñas personales).

## 6. Notas de diseño

- El dinero es BIGINT en centavos.
- Los precios y el nombre del producto se copian al pedido (`unit_price_cents`, `name_snapshot`), para que un cambio futuro en el catálogo no altere los pedidos pasados.
- `courier_positions` crece rápido; se conserva 7 días ⚠ y, si hace falta, se particiona por día.
- Las tablas de analítica (fase 4) se diseñan entonces, separadas de estas.
- El reinicio nocturno vacía la base de la demo completa, no fila por fila.

## 7. Cambios respecto al borrador inicial (2026-11-13)

- Estado nuevo **`en_comercio`** (el repartidor llegó al comercio) entre `asignado` y `en_camino`; el índice que impide dos pedidos activos por repartidor lo incluye.
- Columna **`orders.courier_pay_cents`** y tabla **`ledger_entries`** (pagos de juguete que suman cero por pedido).
- Tablas **`geo_calles`** y **`geo_direcciones`** (geocodificador propio; no tienen relación con las demás).
- La consulta del «más cercano» de la sección 2 es el borrador inicial: la versión final filtra los 8 más cercanos en línea recta con `ST_DWithin` y elige entre ellos por el **tiempo real por calle** que calcula OSRM (ver `app/services/couriers.py`).
- Las migraciones de Alembic son la fuente de verdad del esquema (`alembic/versions/`).
