#!/usr/bin/env bash
# Sync all cached Mailganer API documentation sources.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

python3 "$ROOT/scripts/sync-api-docs.py"
python3 "$ROOT/scripts/sync-postman.py"
python3 "$ROOT/scripts/build-crosslinks.py"
