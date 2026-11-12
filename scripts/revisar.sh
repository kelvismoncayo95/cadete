#!/usr/bin/env bash
# Corre lo mismo que el CI, en local: tests y búsqueda de secretos. Frena si algo falla.
set -euo pipefail
cd "$(dirname "$0")/.."
./venv/bin/pytest
docker run --rm -v "$PWD:/repo" zricethezav/gitleaks:latest detect --source /repo --no-banner
echo "Todo en verde."
