# Plan de implementación

Veinte pasos pequeños, cada uno con su condición de «hecho cuando». **El compromiso son los pasos 0 a 15 (fases 1 a 3).** Los pasos 16 a 19 se deciden después.

## 1. Reglas de trabajo

1. Repositorio nuevo, una rama por paso y commits pequeños; nada directo a main.
2. **Modo bloque:** avanzar sin pausas dentro de un paso. Cada paso termina con tests en verde, commit, merge a main y documentos actualizados. Pausa solo en decisiones importantes de producto o arquitectura, o en algo irreversible o público.
3. Test primero: verlo fallar, escribir el código y verlo pasar. Los tests de concurrencia se prueban rompiendo el código a propósito.
4. Antes de cada commit: pytest y revisar el diff.
5. Solo datos inventados. Nada a GitHub sin el OK del autor.
6. Al cerrar cada paso, anotar en `ESTUDIO.md` qué se aprendió y qué falló.
7. Cada semana, reescribir a mano una pieza central sin ayuda (por ejemplo, la consulta del repartidor más cercano) y practicar explicarla en voz alta.
8. Antes de crear cualquier recurso de AWS: verificar servicios, nivel gratuito y precios en la documentación oficial, y activar una alerta de gasto.
9. Identidad visual propia de Cadete (naranja y Manrope), distinta de clínica y minipay.

## 2. Disponibilidad

2 a 4 horas de lunes a viernes, y algún día de fin de semana, además de repasar minipay una hora por día. Fecha de inicio propuesta: lunes 16 de noviembre de 2026 ⚠.

## 3. Pasos

| N.º | Paso | Qué aprendés justo antes | Hecho cuando |
|---|---|---|---|
| 0 | Repositorio, entorno, .gitignore, README mínimo y documentos privados | venv y estructura | el repo existe, `pytest` corre y las decisiones están anotadas |
| 1 | docker-compose con api, PostgreSQL con PostGIS y Redis, y /health | Docker Compose, PostGIS | `docker compose up` y /health responde 200 |
| 2 | CI mínimo en GitHub Actions | workflows con servicios | cada commit corre pytest y gitleaks |
| 3 | Esquema y migraciones con UUID (usuarios, comercios, productos, pedidos) | Alembic, tipos geográficos | `alembic upgrade head` crea las tablas en una base vacía |
| 4 | Máquina de estados del pedido (TEST PRIMERO) | estados y transiciones | las transiciones válidas pasan y las inválidas dan 409, con historial |
| 5 | Login con usuarios de demo y permisos por rol | JWT, 404 en recursos ajenos | cada rol ve solo lo suyo |
| 6 | Crear pedido con idempotencia y catálogo | idempotencia | confirmar dos veces crea un solo pedido |
| 7 | Acciones del comercio y datos de demo de Montevideo | semillas con coordenadas | un pedido avanza de «recibido» a «listo» |
| 8 | Posiciones de repartidores y consulta del más cercano (TEST PRIMERO) | consultas con PostGIS | con posiciones conocidas siempre sale el más cercano y se respeta el radio |
| 9 | Despacho: oferta, aceptación, expiración y siguiente | SKIP LOCKED, tareas con reintentos | dos pedidos simultáneos con un repartidor: solo uno lo recibe; una oferta vencida pasa al siguiente |
| 10 | Seguimiento en vivo con SSE y simulador de repartidores | SSE, Redis | el cliente ve moverse al repartidor y, al reconectar, recupera el estado |
| 11 | Mapa propio de Montevideo (TOPE: 1 semana) | PMTiles, `pmtiles extract`, MapLibre, estilo | el mapa se ve como el diseño de UX/UI y muestra la atribución |
| 11b | Rutas por calles con OSRM (pedido de Kelvis: nada en línea recta) | grafos dirigidos, snapping, matrices de tiempos | la ruta sigue las calles sin ir en contramano; el «más cercano» es por tiempo de viaje; hay respaldo si OSRM cae |
| 12 | Web para cliente, comercio, repartidor y administrador | HTML, CSS y JS vanilla | un recorrido completo desde el iPhone |
| 13 | AWS con Terraform como ejercicio (alerta de gasto primero) | servicios de AWS, Terraform ⚠ | se levanta, se prueba, se documenta con capturas y se destruye sin dejar nada encendido |
| 14 | Demo pública barata y estable, con despliegue automático y reinicio nocturno | CD, tareas programadas | al hacer merge en main se despliega solo y la demo se reinicia sola |
| 15 | Observabilidad | logs en JSON y métricas | /metrics y una alarma básica funcionan |
| 16 | Analítica: almacén de datos y tablero (fase 4, opcional) | modelado, índices, EXPLAIN | un tablero muestra tiempos de entrega y horas pico |
| 17 | Catálogo con IA y cola de revisión (fase 5, opcional) | API de IA, validación | un menú subido genera productos revisables, y se mide la exactitud |
| 18 | Pagos con minipay (fase 6, opcional) | contratos entre servicios | un pedido se paga de punta a punta, con tests entre los dos |
| 19 | README en inglés, capturas y ESTUDIO.md completo | documentar | el repo está listo para mostrar |

El README en inglés se empieza en el paso 0 y se completa en cada fase; el paso 19 es el pulido final.

## 4. Estimación ⚠

Con 2 a 4 horas por día: de 8 a 10 semanas para los pasos 0 a 15. Es un cálculo, no un compromiso, y se ajusta después de los pasos 4 y 9, que son los más difíciles.

## 5. Definición de terminado (compromiso)

- Los criterios del PRD (sección 9) se cumplen y están probados.
- Hay un test por cada regla y por cada caso alterno.
- gitleaks sin hallazgos y sin datos reales.
- README en inglés con demo en vivo, capturas, cómo correrlo, usuarios de demo, decisiones y limitaciones, y el aviso «datos inventados».
- La demo pública funciona, se reinicia sola, y el ejercicio de AWS quedó documentado y destruido.
- ESTUDIO.md tiene, por cada paso, qué hace, por qué se eligió así, qué falló y preguntas de entrevista con respuestas.

## 6. Después (no ahora)

Fases 4 a 6 · despacho anticipado (mientras el comercio prepara) · modo invitado con cuenta propia · notificaciones · calificaciones de repartidores · más ciudades.
