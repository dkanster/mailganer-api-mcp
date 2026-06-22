#!/usr/bin/env bash
# Bootstrap mailganer-api-mcp: venv, env file, launcher, docs sync.
set -euo pipefail

PACKAGE_ROOT="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "${1:-.}" && pwd)"

LAUNCHER="$ROOT/.cursor/api-mcp.sh"
MCP_JSON="$ROOT/.cursor/mcp.json"
MCP_EXAMPLE="$PACKAGE_ROOT/mcp.json.example"

if [[ -d "$ROOT/ai" ]]; then
  ENV_FILE="$ROOT/ai/.env.api"
else
  ENV_FILE="$ROOT/.env.api"
fi

info() { echo "→ $*"; }
ok() { echo "✓ $*"; }
fail() { echo "✗ $*" >&2; exit 1; }

info "Проект: $ROOT"
command -v python3 >/dev/null 2>&1 || fail "Python 3 не найден"

python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/pip" install -q -e "$PACKAGE_ROOT"
ok "venv + editable install"

mkdir -p "$ROOT/.cursor"
cp "$PACKAGE_ROOT/.cursor/api-mcp.sh" "$LAUNCHER"
chmod +x "$LAUNCHER"
ok "Launcher: .cursor/api-mcp.sh"

python3 - "$MCP_JSON" "$MCP_EXAMPLE" <<'PY'
import json, sys
from pathlib import Path

mcp_path, example_path = Path(sys.argv[1]), Path(sys.argv[2])
entry = {"command": ".cursor/api-mcp.sh", "args": []}

if mcp_path.exists():
    data = json.loads(mcp_path.read_text(encoding="utf-8"))
elif example_path.exists():
    data = json.loads(example_path.read_text(encoding="utf-8"))
else:
    data = {"mcpServers": {}}

data.setdefault("mcpServers", {})["mailganer-api"] = entry
mcp_path.parent.mkdir(parents=True, exist_ok=True)
mcp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
ok "MCP config: .cursor/mcp.json"

if [[ ! -f "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" <<'EOF'
# API key из раздела «Настройки аккаунта» Mailganer
MAILGANER_API_KEY=

# Базовый URL REST API (обычно не меняется)
MAILGANER_API_BASE_URL=https://mailganer.com/api
EOF
  ok "Env: ${ENV_FILE#$ROOT/}"
else
  ok "Env уже есть: ${ENV_FILE#$ROOT/}"
fi

info "Синхронизация документации API..."
"$ROOT/.venv/bin/python" "$PACKAGE_ROOT/scripts/sync-api-docs.py"
"$ROOT/.venv/bin/python" "$PACKAGE_ROOT/scripts/sync-postman.py"
ok "Документация обновлена в docs/"

echo "Готово. Reload MCP в Cursor: Settings → MCP → Reload"
