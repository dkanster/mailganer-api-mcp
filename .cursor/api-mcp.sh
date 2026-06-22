#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env.api"
[[ -d "$ROOT/ai" && -f "$ROOT/ai/.env.api" ]] && ENV_FILE="$ROOT/ai/.env.api"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

exec "$ROOT/.venv/bin/python" "$ROOT/server.py"
