#!/usr/bin/env bash
# Corre lo mismo que el CI, en local: tests y búsqueda de secretos. Frena si algo falla.
set -euo pipefail
cd "$(dirname "$0")/.."
# Los tests necesitan la base y Redis: se levantan (si hace falta) y se espera a que estén sanos.
docker compose up -d --wait postgres redis
./venv/bin/pytest
docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:latest detect --source /repo --no-banner
echo "Todo en verde."
