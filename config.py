"""Mailganer API MCP — configuration."""

from __future__ import annotations

import os
from pathlib import Path


def env_file() -> Path:
    root = Path(__file__).resolve().parent
    ai_env = root / "ai" / ".env.api"
    if ai_env.exists():
        return ai_env
    return root / ".env.api"


def read_env(key: str, default: str = "") -> str:
    path = env_file()
    if not path.exists():
        return os.environ.get(key, default)
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return os.environ.get(key, default)


def api_key() -> str:
    return read_env("MAILGANER_API_KEY")


def base_url() -> str:
    return read_env("MAILGANER_API_BASE_URL", "https://mailganer.com/api")
