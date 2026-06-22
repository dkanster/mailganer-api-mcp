"""Knowledge base helpers for Mailganer API documentation."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from difflib import unified_diff
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DOCS_DIR = ROOT / "docs"
INDEX_FILE = DOCS_DIR / "api-index.json"
POSTMAN_INDEX = DOCS_DIR / "postman-index.json"
CROSSLINKS_FILE = DOCS_DIR / "crosslinks.json"
ENDPOINTS_DIR = DOCS_DIR / "endpoints"
SCRIPTS_DIR = ROOT / "scripts"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_index() -> dict[str, Any]:
    return load_json(INDEX_FILE)


def load_postman_index() -> dict[str, Any]:
    return load_json(POSTMAN_INDEX)


def load_crosslinks() -> dict[str, Any]:
    return load_json(CROSSLINKS_FILE)


def normalize_api_path(path: str) -> str:
    path = path.split("?")[0].strip()
    match = re.search(r"https?://[^/]+(/[^\s?#]+)", path)
    if match:
        path = match.group(1)
    path = re.sub(r"\{\{([^}]+)\}\}", r":\1", path)
    if not path.startswith("/"):
        path = f"/{path}"
    if not path.endswith("/"):
        path = f"{path}/"
    return path.lower()


def parse_doc_api_call(raw: str) -> tuple[str, str] | None:
    match = re.match(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(https?://[^\s]+|/[^\s]+)", raw.strip(), re.I)
    if not match:
        return None
    return match.group(1).upper(), normalize_api_path(match.group(2))


def postman_key(method: str, path: str, *, name: str | None = None) -> str:
    base = f"{method.upper()} {normalize_api_path(path)}"
    if name:
        return f"{base} | {name.strip()}"
    return base


def _normalize_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text.strip().lower())
    text = re.sub(r"[^\w\sа-яё-]", "", text, flags=re.I)
    return text


def _title_similarity(left: str, right: str) -> float:
    a = _normalize_title(left)
    b = _normalize_title(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.85
    a_words = set(a.split())
    b_words = set(b.split())
    if not a_words or not b_words:
        return 0.0
    return len(a_words & b_words) / len(a_words | b_words)


def _postman_summary(item: dict[str, Any], *, match_reason: str, score: float) -> dict[str, Any]:
    description = _strip_html(item.get("description", ""))
    return {
        "name": item.get("name"),
        "method": item.get("method"),
        "path": item.get("path"),
        "url": item.get("url"),
        "folder": item.get("folder"),
        "description_plain": description[:2000] if description else "",
        "match_reason": match_reason,
        "match_score": round(score, 3),
    }


def _doc_summary(slug: str, doc: dict[str, Any], *, match_reason: str, score: float) -> dict[str, Any]:
    return {
        "slug": slug,
        "title": doc.get("title"),
        "category": doc.get("category"),
        "path": doc.get("path"),
        "url": doc.get("url"),
        "endpoints": doc.get("endpoints", []),
        "match_reason": match_reason,
        "match_score": round(score, 3),
    }


def find_postman_for_doc(doc: dict[str, Any], postman_requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    doc_calls = [call for raw in doc.get("endpoints", []) if (call := parse_doc_api_call(raw))]
    if not doc_calls:
        return []

    candidates: list[tuple[float, dict[str, Any], str]] = []
    doc_title = doc.get("title", "")

    for item in postman_requests:
        key = postman_key(item.get("method", ""), item.get("path", ""))
        for method, path in doc_calls:
            if key != postman_key(method, path):
                continue
            title_score = _title_similarity(doc_title, item.get("name", ""))
            score = 0.6 + 0.4 * title_score
            reason = "method_path+title" if title_score >= 0.5 else "method_path"
            candidates.append((score, item, reason))

    if not candidates and len(doc_calls) == 1:
        method, path = doc_calls[0]
        for item in postman_requests:
            if postman_key(item.get("method", ""), item.get("path", "")) == postman_key(method, path):
                candidates.append((0.5, item, "method_path_only"))

    candidates.sort(key=lambda row: row[0], reverse=True)
    seen_names: set[str] = set()
    results: list[dict[str, Any]] = []
    for score, item, reason in candidates:
        name = item.get("name", "")
        if name in seen_names:
            continue
        seen_names.add(name)
        results.append(_postman_summary(item, match_reason=reason, score=score))

    if len(results) > 1 and doc_title:
        best_title = max(_title_similarity(doc_title, item["name"]) for item in results)
        if best_title >= 0.5:
            results = [
                item
                for item in results
                if _title_similarity(doc_title, item["name"]) >= max(0.35, best_title - 0.15)
            ]

    return results[:5]


def find_docs_for_postman(
    request: dict[str, Any],
    *,
    slug_docs: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    key = postman_key(request.get("method", ""), request.get("path", ""))
    req_name = request.get("name", "")
    matches: list[tuple[float, str, dict[str, Any], str]] = []

    for slug, doc in slug_docs.items():
        doc_calls = [call for raw in doc.get("endpoints", []) if (call := parse_doc_api_call(raw))]
        if not any(postman_key(method, path) == key for method, path in doc_calls):
            continue
        title_score = _title_similarity(doc.get("title", ""), req_name)
        score = 0.6 + 0.4 * title_score
        reason = "method_path+title" if title_score >= 0.5 else "method_path"
        matches.append((score, slug, doc, reason))

    matches.sort(key=lambda row: row[0], reverse=True)
    if len(matches) > 1 and req_name:
        best_title = max(_title_similarity(doc.get("title", ""), req_name) for _, _, doc, _ in matches)
        if best_title >= 0.5:
            matches = [
                row
                for row in matches
                if _title_similarity(row[2].get("title", ""), req_name) >= max(0.35, best_title - 0.15)
            ]

    return [_doc_summary(slug, doc, match_reason=reason, score=score) for score, slug, doc, reason in matches[:5]]


def build_crosslinks(*, save: bool = False) -> dict[str, Any]:
    postman = load_postman_index()
    postman_requests = postman.get("requests", [])

    slug_docs: dict[str, dict[str, Any]] = {}
    for path in ENDPOINTS_DIR.glob("*.json"):
        slug_docs[path.stem] = load_json(path)

    by_slug: dict[str, dict[str, Any]] = {}
    by_postman: dict[str, list[dict[str, Any]]] = {}
    unmatched_docs: list[str] = []
    total_links = 0

    for slug, doc in slug_docs.items():
        related = find_postman_for_doc(doc, postman_requests)
        by_slug[slug] = {
            "title": doc.get("title"),
            "doc_path": doc.get("path"),
            "postman_requests": related,
        }
        if related:
            total_links += len(related)
            for item in related:
                key = postman_key(item["method"], item["path"], name=item["name"])
                by_postman.setdefault(key, [])
                entry = _doc_summary(slug, doc, match_reason=item["match_reason"], score=item["match_score"])
                if entry not in by_postman[key]:
                    by_postman[key].append(entry)
        else:
            unmatched_docs.append(slug)

    matched_postman_keys = set(by_postman.keys())
    all_postman_keys = {
        postman_key(item.get("method", ""), item.get("path", ""), name=item.get("name", ""))
        for item in postman_requests
    }
    unmatched_postman = sorted(all_postman_keys - matched_postman_keys)

    payload = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "by_slug": by_slug,
        "by_postman": by_postman,
        "stats": {
            "docs_total": len(slug_docs),
            "postman_total": len(postman_requests),
            "docs_with_postman": sum(1 for item in by_slug.values() if item["postman_requests"]),
            "postman_with_docs": len(by_postman),
            "total_links": total_links,
            "unmatched_docs": unmatched_docs,
            "unmatched_postman": unmatched_postman,
        },
    }

    if save:
        CROSSLINKS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return payload


def get_linked_endpoint_doc(slug: str) -> dict[str, Any]:
    doc = load_endpoint(slug)
    if doc is None:
        return {"error": f"Endpoint doc not found: {slug}"}

    crosslinks = load_crosslinks()
    linked = crosslinks.get("by_slug", {}).get(slug)
    if linked and linked.get("postman_requests"):
        postman_requests = linked["postman_requests"]
    else:
        postman_requests = find_postman_for_doc(doc, load_postman_index().get("requests", []))

    return {
        "slug": slug,
        "doc": doc,
        "postman_requests": postman_requests,
        "sources": {
            "doc_url": doc.get("url"),
            "postman_collection": load_postman_index().get("source"),
        },
    }


def get_linked_postman_request(*, name: str | None = None, path: str | None = None) -> dict[str, Any]:
    request = get_postman_request(name=name, path=path)
    if request is None:
        return {"error": "Postman request not found"}

    crosslinks = load_crosslinks()
    key = postman_key(
        request.get("method", ""),
        request.get("path", ""),
        name=request.get("name", ""),
    )
    related_docs = crosslinks.get("by_postman", {}).get(key, [])

    if not related_docs:
        slug_docs = {path.stem: load_json(path) for path in ENDPOINTS_DIR.glob("*.json")}
        related_docs = find_docs_for_postman(request, slug_docs=slug_docs)

    description = _strip_html(request.get("description", ""))
    return {
        "postman_request": {
            **request,
            "description_plain": description,
        },
        "related_docs": related_docs,
    }


def load_endpoint(slug: str) -> dict[str, Any] | None:
    path = ENDPOINTS_DIR / f"{slug}.json"
    if not path.exists():
        return None
    return load_json(path)


def get_doc_status() -> dict[str, Any]:
    index = load_index()
    postman = load_postman_index()
    stats = index.get("stats", {})
    postman_stats = postman.get("stats", {})
    endpoint_files = sorted(p.name for p in ENDPOINTS_DIR.glob("*.json"))

    return {
        "api_docs": {
            "synced_at": index.get("synced_at"),
            "sources": index.get("sources", {}),
            "pages_scraped": stats.get("pages_scraped"),
            "pages_total": stats.get("pages_total"),
            "pages_failed": stats.get("pages_failed"),
            "pages_new_last_sync": stats.get("pages_new"),
            "categories": stats.get("categories"),
            "failures": index.get("failures", []),
            "endpoint_files": len(endpoint_files),
        },
        "postman": {
            "synced_at": postman.get("synced_at"),
            "collection_name": postman.get("collection_name"),
            "requests_total": postman_stats.get("requests_total"),
            "folders_total": postman_stats.get("folders_total"),
            "source": postman.get("source"),
        },
        "sitemap": index.get("sitemap", {}),
        "overview_exists": (DOCS_DIR / "overview.md").exists(),
        "crosslinks": load_crosslinks().get("stats", {}),
    }


def list_api_docs(*, category: str | None = None) -> list[dict[str, Any]]:
    index = load_index()
    items = index.get("endpoints", [])
    if category:
        needle = category.lower()
        items = [item for item in items if needle in item.get("category", "").lower()]
    return items


def _endpoint_search_text(doc: dict[str, Any]) -> str:
    parts = [
        doc.get("title", ""),
        doc.get("path", ""),
        doc.get("category", ""),
        " ".join(doc.get("http_methods", [])),
        " ".join(doc.get("endpoints", [])),
        " ".join(doc.get("headings", [])),
        " ".join(doc.get("paragraphs", [])),
    ]
    for example in doc.get("code_examples", []):
        if isinstance(example, dict):
            parts.append(example.get("label", ""))
            parts.append(example.get("code", ""))
        else:
            parts.append(str(example))
    return " ".join(parts).lower()


def search_api_docs(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    needle = query.lower().strip()
    if not needle:
        return []

    matches: list[tuple[int, dict[str, Any]]] = []
    for path in ENDPOINTS_DIR.glob("*.json"):
        doc = load_json(path)
        haystack = _endpoint_search_text(doc)
        if needle not in haystack:
            continue
        score = haystack.count(needle)
        matches.append(
            (
                score,
                {
                    "slug": path.stem,
                    "title": doc.get("title"),
                    "category": doc.get("category"),
                    "path": doc.get("path"),
                    "url": doc.get("url"),
                    "endpoints": doc.get("endpoints", []),
                    "scraped_at": doc.get("scraped_at"),
                },
            )
        )

    matches.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in matches[:limit]]


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def search_postman(query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    needle = query.lower().strip()
    if not needle:
        return []

    index = load_postman_index()
    matches: list[dict[str, Any]] = []
    for item in index.get("requests", []):
        haystack = " ".join(
            [
                item.get("name", ""),
                item.get("method", ""),
                item.get("path", ""),
                item.get("folder", ""),
                _strip_html(item.get("description", "")),
            ]
        ).lower()
        if needle in haystack:
            matches.append(item)
        if len(matches) >= limit:
            break
    return matches


def get_postman_request(*, name: str | None = None, path: str | None = None) -> dict[str, Any] | None:
    index = load_postman_index()
    for item in index.get("requests", []):
        if name and name.lower() in item.get("name", "").lower():
            return item
        if path and item.get("path", "").lower() == path.lower():
            return item
    return None


def _load_sync_module():
    script = SCRIPTS_DIR / "sync-api-docs.py"
    spec = importlib.util.spec_from_file_location("sync_api_docs", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load sync module from {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_doc_page(slug: str) -> dict[str, Any]:
    cached = load_endpoint(slug)
    if cached is None:
        return {"error": f"Cached doc not found: {slug}"}

    sync_mod = _load_sync_module()
    url = cached["url"]
    html = sync_mod.fetch(url)
    live = sync_mod.parse_endpoint_page(
        html,
        path=cached["path"],
        menu_title=cached.get("title", slug),
        category=cached.get("category", ""),
    ).to_dict()

    compare_fields = ["title", "http_methods", "endpoints", "headings", "paragraphs", "code_examples"]
    changes: dict[str, Any] = {}
    for field in compare_fields:
        if cached.get(field) != live.get(field):
            changes[field] = {"cached": cached.get(field), "live": live.get(field)}

    cached_text = json.dumps({k: cached.get(k) for k in compare_fields}, ensure_ascii=False, indent=2)
    live_text = json.dumps({k: live.get(k) for k in compare_fields}, ensure_ascii=False, indent=2)
    diff_lines = list(
        unified_diff(
            cached_text.splitlines(),
            live_text.splitlines(),
            fromfile=f"cached/{slug}.json",
            tofile=f"live/{slug}",
            lineterm="",
        )
    )

    return {
        "slug": slug,
        "url": url,
        "cached_scraped_at": cached.get("scraped_at"),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "changed": bool(changes),
        "changed_fields": sorted(changes.keys()),
        "changes": changes,
        "diff": "\n".join(diff_lines[:200]),
    }


def sync_documentation(*, target: str = "all") -> dict[str, Any]:
    results: dict[str, Any] = {"started_at": datetime.now(timezone.utc).isoformat(), "steps": []}

    if target in {"all", "api"}:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "sync-api-docs.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        results["steps"].append(
            {
                "name": "api_docs",
                "exit_code": proc.returncode,
                "stdout": proc.stdout[-4000:] if proc.stdout else "",
                "stderr": proc.stderr[-2000:] if proc.stderr else "",
            }
        )

    if target in {"all", "postman"}:
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "sync-postman.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        results["steps"].append(
            {
                "name": "postman",
                "exit_code": proc.returncode,
                "stdout": proc.stdout[-2000:] if proc.stdout else "",
                "stderr": proc.stderr[-2000:] if proc.stderr else "",
            }
        )

    if target == "all" and all(step["exit_code"] == 0 for step in results["steps"]):
        crosslinks = build_crosslinks(save=True)
        results["crosslinks"] = crosslinks["stats"]
    elif target in {"all", "api", "postman"}:
        try:
            crosslinks = build_crosslinks(save=True)
            results["crosslinks"] = crosslinks["stats"]
        except Exception as exc:  # noqa: BLE001
            results["crosslinks_error"] = str(exc)

    results["finished_at"] = datetime.now(timezone.utc).isoformat()
    results["status"] = get_doc_status()
    results["success"] = all(step["exit_code"] == 0 for step in results["steps"])
    return results
