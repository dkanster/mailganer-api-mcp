#!/usr/bin/env python3
"""Sync Mailganer Postman collection into docs/postman/."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POSTMAN_VIEW_URL = "https://documenter.getpostman.com/view/23131434/VUxPvnhA"
POSTMAN_COLLECTION_URL = (
    "https://documenter.gw.postman.com/api/collections/23131434/VUxPvnhA"
    "?segregateAuth=true&versionTag=latest"
)
USER_AGENT = "mailganer-api-mcp-postman-sync/0.1"


def fetch(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_path(raw_url: str) -> str:
    if not raw_url:
        return ""
    match = re.search(r"https?://[^/]+(/[^\s?#]+)", raw_url)
    if match:
        return match.group(1)
    if raw_url.startswith("/"):
        return raw_url.split("?")[0]
    return raw_url.split("?")[0]


def walk_items(
    items: list[dict[str, Any]],
    *,
    folder: str = "",
) -> list[dict[str, str]]:
    requests: list[dict[str, str]] = []
    for item in items:
        name = item.get("name", "")
        if "item" in item:
            subfolder = f"{folder}/{name}" if folder else name
            requests.extend(walk_items(item["item"], folder=subfolder))
            continue
        request = item.get("request")
        if not isinstance(request, dict):
            continue
        method = str(request.get("method", "GET")).upper()
        url_obj = request.get("url")
        raw_url = ""
        if isinstance(url_obj, str):
            raw_url = url_obj
        elif isinstance(url_obj, dict):
            raw = url_obj.get("raw")
            if isinstance(raw, str):
                raw_url = raw
            else:
                path_parts = url_obj.get("path") or []
                if isinstance(path_parts, list):
                    raw_url = "/" + "/".join(str(part) for part in path_parts)
        description = ""
        desc = request.get("description")
        if isinstance(desc, str):
            description = desc.strip()
        elif isinstance(desc, dict):
            content = desc.get("content")
            if isinstance(content, str):
                description = content.strip()
        requests.append(
            {
                "name": name,
                "method": method,
                "path": extract_path(raw_url),
                "url": raw_url,
                "description": description,
                "folder": folder,
            }
        )
    return requests


def sync_postman(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    postman_dir = output_dir / "postman"
    postman_dir.mkdir(exist_ok=True)

    collection_text = fetch(POSTMAN_COLLECTION_URL)
    collection = json.loads(collection_text)
    collection_path = postman_dir / "collection.json"
    collection_path.write_text(
        json.dumps(collection, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    requests = walk_items(collection.get("item", []))
    index = {
        "source": POSTMAN_VIEW_URL,
        "collection_api_url": POSTMAN_COLLECTION_URL,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "collection_name": collection.get("info", {}).get("name", ""),
        "collection_id": collection.get("info", {}).get("_postman_id", ""),
        "requests": requests,
        "stats": {
            "requests_total": len(requests),
            "folders_total": len({item["folder"] for item in requests if item["folder"]}),
        },
    }
    index_path = output_dir / "postman-index.json"
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "docs",
        help="Output directory (default: docs/)",
    )
    args = parser.parse_args()

    try:
        result = sync_postman(args.output)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        print(f"Postman sync failed: {exc}", file=sys.stderr)
        return 1

    stats = result["stats"]
    print(f"✓ Postman collection: {result['collection_name']}")
    print(f"  Requests: {stats['requests_total']}, folders: {stats['folders_total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
