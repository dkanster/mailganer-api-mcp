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
MANUAL_CROSSLINKS_FILE = DOCS_DIR / "manual-crosslinks.json"
ENDPOINTS_DIR = DOCS_DIR / "endpoints"
SCRIPTS_DIR = ROOT / "scripts"

PATH_ALIASES: dict[str, list[str]] = {
    "/api/v2/auth/": ["/api/auth/"],
    "/api/auth/": ["/api/v2/auth/"],
}


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


def load_manual_crosslinks() -> dict[str, Any]:
    if not MANUAL_CROSSLINKS_FILE.exists():
        return {"doc_to_postman": {}, "doc_notes": {}, "postman_to_doc": {}}
    return load_json(MANUAL_CROSSLINKS_FILE)


def normalize_api_path(path: str) -> str:
    path = path.split("?")[0].strip()
    match = re.search(r"https?://[^/]+(/[^\s?#]+)", path)
    if match:
        path = match.group(1)
    path = re.sub(r"\{\{([^}]+)\}\}", r":\1", path)
    path = re.sub(r"\{([^}/]+)\}", r":\1", path)
    if not path.startswith("/"):
        path = f"/{path}"
    if not path.endswith("/"):
        path = f"{path}/"
    return path.lower()


def path_aliases(path: str) -> set[str]:
    normalized = normalize_api_path(path)
    aliases = {normalized}
    for base, equivalents in PATH_ALIASES.items():
        if normalized == normalize_api_path(base):
            aliases.update(normalize_api_path(item) for item in equivalents)
    return aliases


def _path_segments(path: str) -> list[str]:
    return [segment for segment in normalize_api_path(path).strip("/").split("/") if segment]


def _segment_matches(left: str, right: str) -> bool:
    if left == right:
        return True
    if left.startswith(":") or right.startswith(":"):
        return True
    return False


def paths_match(left: str, right: str) -> bool:
    left_segments = _path_segments(left)
    right_segments = _path_segments(right)
    if len(left_segments) != len(right_segments):
        return False
    return all(_segment_matches(a, b) for a, b in zip(left_segments, right_segments))


def api_calls_match(doc_method: str, doc_path: str, postman_method: str, postman_path: str) -> bool:
    if doc_method.upper() != postman_method.upper():
        return False
    doc_aliases = path_aliases(doc_path)
    postman_aliases = path_aliases(postman_path)
    for left in doc_aliases:
        for right in postman_aliases:
            if paths_match(left, right):
                return True
    return False


def parse_doc_api_call(raw: str) -> tuple[str, str] | None:
    match = re.match(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(https?://[^\s]+|/[^\s]+)", raw.strip(), re.I)
    if not match:
        return None
    return match.group(1).upper(), normalize_api_path(match.group(2))


def _infer_curl_method(code: str) -> str:
    for pattern in (
        r"--request\s+(GET|POST|PUT|PATCH|DELETE)",
        r"-X\s+(GET|POST|PUT|PATCH|DELETE)",
    ):
        match = re.search(pattern, code, re.I)
        if match:
            return match.group(1).upper()
    if "--data" in code or "--form" in code:
        return "POST"
    return "GET"


def _should_extract_urls_from_example(code: str, label: str) -> bool:
    if "curl" in code.lower():
        return True
    if parse_doc_api_call(code):
        return True
    label_lower = label.lower()
    return any(token in label_lower for token in ("запрос", "request", "endpoint", "curl", "api"))


def extract_doc_api_calls(doc: dict[str, Any]) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add_call(method: str, path: str) -> None:
        key = (method.upper(), normalize_api_path(path))
        if key in seen:
            return
        seen.add(key)
        calls.append(key)

    for raw in doc.get("endpoints", []):
        if parsed := parse_doc_api_call(raw):
            add_call(*parsed)

    if not doc.get("endpoints"):
        return calls

    default_methods = [method.upper() for method in doc.get("http_methods", [])]

    for example in doc.get("code_examples", []):
        code = example.get("code", "") if isinstance(example, dict) else str(example)
        label = example.get("label", "") if isinstance(example, dict) else ""
        if not code or not _should_extract_urls_from_example(code, label):
            continue
        if parsed := parse_doc_api_call(code):
            add_call(*parsed)
            continue
        for url_match in re.finditer(r"https://mailganer\.com(/api/[^\s'\"\\]+)", code):
            method = _infer_curl_method(code) if "curl" in code.lower() else (default_methods[0] if len(default_methods) == 1 else "GET")
            add_call(method, url_match.group(1))

    return calls


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


def _merge_postman_matches(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            name = item.get("name", "")
            if name in seen:
                continue
            seen.add(name)
            merged.append(item)
    return merged[:8]


def _find_postman_by_name(name: str, postman_requests: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in postman_requests:
        if item.get("name") == name:
            return item
    return None


def _manual_postman_for_doc(
    slug: str,
    manual: dict[str, Any],
    postman_requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name in manual.get("doc_to_postman", {}).get(slug, []):
        item = _find_postman_by_name(name, postman_requests)
        if item is None:
            continue
        results.append(_postman_summary(item, match_reason="manual", score=1.0))
    return results


def find_postman_for_doc(doc: dict[str, Any], postman_requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    doc_calls = extract_doc_api_calls(doc)
    if not doc_calls:
        return []

    candidates: list[tuple[float, dict[str, Any], str]] = []
    doc_title = doc.get("title", "")

    for item in postman_requests:
        for method, path in doc_calls:
            if not api_calls_match(method, path, item.get("method", ""), item.get("path", "")):
                continue
            title_score = _title_similarity(doc_title, item.get("name", ""))
            score = 0.6 + 0.4 * title_score
            reason = "method_path+title" if title_score >= 0.5 else "method_path"
            candidates.append((score, item, reason))

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

    return results


def find_docs_for_postman(
    request: dict[str, Any],
    *,
    slug_docs: dict[str, dict[str, Any]],
    manual: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    req_name = request.get("name", "")
    matches: list[tuple[float, str, dict[str, Any], str]] = []

    if manual:
        for slug, names in manual.get("doc_to_postman", {}).items():
            if req_name not in names:
                continue
            doc = slug_docs.get(slug)
            if doc is None:
                continue
            matches.append((1.0, slug, doc, "manual"))

    for slug, doc in slug_docs.items():
        if any(entry[1] == slug for entry in matches):
            continue
        doc_calls = extract_doc_api_calls(doc)
        if not any(
            api_calls_match(method, path, request.get("method", ""), request.get("path", ""))
            for method, path in doc_calls
        ):
            continue
        title_score = _title_similarity(doc.get("title", ""), req_name)
        score = 0.6 + 0.4 * title_score
        reason = "method_path+title" if title_score >= 0.5 else "method_path"
        matches.append((score, slug, doc, reason))

    matches.sort(key=lambda row: row[0], reverse=True)
    if len(matches) > 1 and req_name and not any(reason == "manual" for *_, reason in matches):
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
    manual = load_manual_crosslinks()

    slug_docs: dict[str, dict[str, Any]] = {}
    for path in ENDPOINTS_DIR.glob("*.json"):
        slug_docs[path.stem] = load_json(path)

    by_slug: dict[str, dict[str, Any]] = {}
    by_postman: dict[str, list[dict[str, Any]]] = {}
    unmatched_docs: list[str] = []
    documented_gaps: list[dict[str, str]] = []
    total_links = 0
    manual_links = 0

    doc_notes = manual.get("doc_notes", {})

    for slug, doc in slug_docs.items():
        auto_related = find_postman_for_doc(doc, postman_requests)
        manual_related = _manual_postman_for_doc(slug, manual, postman_requests)
        related = _merge_postman_matches(auto_related, manual_related)
        manual_links += sum(1 for item in related if item.get("match_reason") == "manual")

        note = doc_notes.get(slug, "")
        by_slug[slug] = {
            "title": doc.get("title"),
            "doc_path": doc.get("path"),
            "postman_requests": related,
            "doc_note": note,
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
            if note:
                documented_gaps.append({"slug": slug, "note": note})

    matched_postman_keys = set(by_postman.keys())
    all_postman_keys = {
        postman_key(item.get("method", ""), item.get("path", ""), name=item.get("name", ""))
        for item in postman_requests
    }
    unmatched_postman = sorted(all_postman_keys - matched_postman_keys)

    payload = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "manual_crosslinks_file": "manual-crosslinks.json",
        "by_slug": by_slug,
        "by_postman": by_postman,
        "stats": {
            "docs_total": len(slug_docs),
            "postman_total": len(postman_requests),
            "docs_with_postman": sum(1 for item in by_slug.values() if item["postman_requests"]),
            "postman_with_docs": len(by_postman),
            "total_links": total_links,
            "manual_links": manual_links,
            "unmatched_docs": unmatched_docs,
            "unmatched_postman": unmatched_postman,
            "documented_gaps": documented_gaps,
            "undocumented_unmatched_docs": [
                slug for slug in unmatched_docs if slug not in doc_notes
            ],
        },
    }

    if save:
        CROSSLINKS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return payload


def list_crosslink_gaps() -> dict[str, Any]:
    crosslinks = load_crosslinks()
    stats = crosslinks.get("stats", {})
    manual = load_manual_crosslinks()

    unmatched_postman_details: list[dict[str, Any]] = []
    postman_index = {postman_key(item["method"], item["path"], name=item["name"]): item for item in load_postman_index().get("requests", [])}
    for key in stats.get("unmatched_postman", []):
        item = postman_index.get(key)
        if item:
            unmatched_postman_details.append(
                {
                    "name": item.get("name"),
                    "method": item.get("method"),
                    "path": item.get("path"),
                    "folder": item.get("folder"),
                }
            )

    unmatched_doc_details: list[dict[str, Any]] = []
    for slug in stats.get("unmatched_docs", []):
        doc = load_endpoint(slug)
        unmatched_doc_details.append(
            {
                "slug": slug,
                "title": doc.get("title") if doc else slug,
                "note": manual.get("doc_notes", {}).get(slug, ""),
            }
        )

    return {
        "summary": stats,
        "unmatched_docs": unmatched_doc_details,
        "unmatched_postman": unmatched_postman_details,
        "manual_crosslinks_file": str(MANUAL_CROSSLINKS_FILE.relative_to(ROOT)),
    }


def get_linked_endpoint_doc(slug: str) -> dict[str, Any]:
    doc = load_endpoint(slug)
    if doc is None:
        return {"error": f"Endpoint doc not found: {slug}"}

    crosslinks = load_crosslinks()
    linked = crosslinks.get("by_slug", {}).get(slug)
    manual = load_manual_crosslinks()
    if linked and linked.get("postman_requests"):
        postman_requests = linked["postman_requests"]
    else:
        auto = find_postman_for_doc(doc, load_postman_index().get("requests", []))
        manual_items = _manual_postman_for_doc(slug, manual, load_postman_index().get("requests", []))
        postman_requests = _merge_postman_matches(auto, manual_items)

    doc_note = linked.get("doc_note") if linked else manual.get("doc_notes", {}).get(slug, "")

    return {
        "slug": slug,
        "doc": doc,
        "postman_requests": postman_requests,
        "doc_note": doc_note,
        "sources": {
            "doc_url": doc.get("url"),
            "postman_collection": load_postman_index().get("source"),
            "manual_crosslinks": str(MANUAL_CROSSLINKS_FILE.relative_to(ROOT)),
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
        related_docs = find_docs_for_postman(request, slug_docs=slug_docs, manual=load_manual_crosslinks())

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
