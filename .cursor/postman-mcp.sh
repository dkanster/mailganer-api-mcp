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

if [[ -z "${POSTMAN_API_KEY:-}" ]]; then
  echo "POSTMAN_API_KEY не задан. Добавьте ключ в .env.api:" >&2
  echo "  https://go.postman.co/settings/me/api-keys" >&2
  exit 1
fi

exec npx -y @postman/postman-mcp-server --code "$@"
