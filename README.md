# Cadete

Ordering and delivery platform for Montevideo, Uruguay. A customer orders from a shop, the shop prepares the order, the system dispatches the nearest courier, and the customer follows the delivery on a live map.

> **Demo project. All data is made up.** No real money, no real people, no real businesses.

*Cadete* is the River Plate word for "delivery rider".

## Status

Work in progress. Steps 0-1 done (repo, environment, Docker Compose with PostGIS and Redis, `/health`).

## Planned stack

Python 3.12 · FastAPI · PostgreSQL 17 + PostGIS · Redis · SSE for live tracking · MapLibre GL JS with a custom map style of Montevideo (OpenStreetMap data) · Docker Compose · GitHub Actions · Terraform on AWS (as an exercise).

## Design documents

See [`docs/`](docs/): PRD, TRD, App Flow, UX/UI, Backend Schema and the step-by-step Plan (written in Spanish).

## Run with Docker

```bash
cp .env.example .env   # then set POSTGRES_PASSWORD
docker compose up -d --build
curl http://localhost:8001/health   # {"status":"ok"}
```

## Run the tests

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
pytest -v
```

## Map data

Map data © OpenStreetMap contributors.
