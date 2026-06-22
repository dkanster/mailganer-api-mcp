#!/usr/bin/env python3
"""Sync Mailganer REST API documentation into docs/."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "https://mailganer.com"
DOCS_ROOT = f"{BASE_URL}/documentation"
API_INDEX_PATH = "/documentation/api/"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"
SITEMAP_FILTER = "/documentation/"
USER_AGENT = "mailganer-api-mcp-docs-sync/0.1"
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


@dataclass
class EndpointPage:
    path: str
    title: str
    category: str
    url: str
    http_methods: list[str] = field(default_factory=list)
    endpoints: list[str] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    code_examples: list[dict[str, str]] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    scraped_at: str = ""

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "title": self.title,
            "category": self.category,
            "url": self.url,
            "http_methods": self.http_methods,
            "endpoints": self.endpoints,
            "headings": self.headings,
            "paragraphs": self.paragraphs,
            "code_examples": self.code_examples,
            "tables": self.tables,
            "scraped_at": self.scraped_at,
        }


def fetch(url: str, timeout: int = 60, retries: int = 3) -> str:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


def clean_text(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def slug_from_path(path: str) -> str:
    slug = path.removeprefix("/documentation/").strip("/")
    slug = slug.replace("/", "-")
    return slug or "index"


def normalize_doc_path(path: str) -> str:
    parsed = urllib.parse.urlparse(path)
    normalized = parsed.path if parsed.scheme else path
    normalized = normalized.rstrip("/") or "/"
    if normalized != "/" and not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized


def is_documentation_url(url: str) -> bool:
    path = normalize_doc_path(url)
    return SITEMAP_FILTER in f"{path}/" or path == "/documentation"


def parse_sitemap(xml_text: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    pages: list[dict[str, str]] = []
    seen: set[str] = set()

    for url_el in root.findall(".//sm:url", NS):
        loc_el = url_el.find("sm:loc", NS)
        if loc_el is None or not loc_el.text:
            continue
        url = loc_el.text.strip()
        if not is_documentation_url(url):
            continue
        path = normalize_doc_path(url)
        if path in seen:
            continue
        seen.add(path)
        lastmod_el = url_el.find("sm:lastmod", NS)
        pages.append(
            {
                "path": path,
                "url": f"{BASE_URL}{path}" if path.startswith("/") else url,
                "slug": slug_from_path(path),
                "lastmod": lastmod_el.text.strip() if lastmod_el is not None and lastmod_el.text else "",
            }
        )

    pages.sort(key=lambda item: item["path"])
    return pages


def fetch_sitemap_pages() -> list[dict[str, str]]:
    xml_text = fetch(SITEMAP_URL)
    return parse_sitemap(xml_text)


def save_sitemap_pages(output_dir: Path, pages: list[dict[str, str]]) -> None:
    payload = {
        "source": SITEMAP_URL,
        "filter": SITEMAP_FILTER,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "pages": pages,
        "stats": {"pages_total": len(pages)},
    }
    (output_dir / "sitemap-pages.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def merge_page_sources(
    sitemap_pages: list[dict[str, str]],
    categories: dict[str, list[dict[str, str]]],
) -> tuple[list[tuple[str, dict[str, str], str]], dict[str, int]]:
    merged: list[tuple[str, dict[str, str], str]] = []
    seen_paths: set[str] = set()
    stats = {"from_sitemap": 0, "from_menu": 0}

    menu_by_path: dict[str, tuple[str, dict[str, str]]] = {}
    for category, items in categories.items():
        for item in items:
            path = normalize_doc_path(item["path"])
            menu_by_path[path] = (category, {**item, "path": path, "slug": slug_from_path(path)})

    for page in sitemap_pages:
        path = normalize_doc_path(page["path"])
        if path in seen_paths:
            continue
        seen_paths.add(path)
        if path in menu_by_path:
            category, item = menu_by_path[path]
            merged.append((category, item, "sitemap"))
        else:
            title = path.removeprefix("/documentation/").replace("/", " ").strip() or "Documentation"
            merged.append(
                (
                    "Sitemap",
                    {
                        "path": path,
                        "title": title,
                        "url": f"{BASE_URL}{path}",
                        "slug": slug_from_path(path),
                    },
                    "sitemap",
                )
            )
        stats["from_sitemap"] += 1

    for category, items in categories.items():
        for item in items:
            path = normalize_doc_path(item["path"])
            if path in seen_paths:
                continue
            seen_paths.add(path)
            merged.append((category, {**item, "path": path, "slug": slug_from_path(path)}, "menu"))
            stats["from_menu"] += 1

    return merged, stats


def parse_menu(html_text: str) -> dict[str, list[dict[str, str]]]:
    categories: dict[str, list[dict[str, str]]] = {}
    blocks = re.findall(
        r't830m__list-title-text[^>]*>\s*([^<]+)\s*</div>\s*</div>\s*'
        r'<div class="t830m__submenu[^"]*">\s*(.*?)</div>\s*</div>\s*</div>',
        html_text,
        re.S,
    )
    for category_raw, submenu in blocks:
        category = re.sub(r"\s+", " ", category_raw.strip())
        items: list[dict[str, str]] = []
        for match in re.finditer(r'href="(/documentation/[^"#?]+)"[^>]*>\s*([^<]+)', submenu):
            path = match.group(1).rstrip("/")
            title = re.sub(r"\s+", " ", match.group(2).strip())
            if path == "/documentation/api":
                continue
            items.append(
                {
                    "path": path,
                    "title": title,
                    "url": f"{BASE_URL}{path}",
                    "slug": slug_from_path(path),
                }
            )
        if items:
            categories[category] = items
    return categories


def is_noise_paragraph(text: str) -> bool:
    if "#rec" in text or ".t-btn" in text:
        return True
    if text.startswith("{") and '"count"' in text:
        return True
    return False


def parse_overview_sections(html_text: str) -> list[dict[str, str | list[str]]]:
    sections: list[dict[str, str | list[str]]] = []
    blocks = re.split(r'(?=<div id="rec\d+")', html_text)
    heading_blocks: list[tuple[int, str]] = []

    for index, block in enumerate(blocks):
        heading_match = re.search(r'class="t026__title[^"]*"[^>]*>([^<]+)', block)
        if not heading_match:
            continue
        heading = clean_text(heading_match.group(1))
        if heading:
            heading_blocks.append((index, heading))

    for pos, (block_index, heading) in enumerate(heading_blocks):
        next_index = heading_blocks[pos + 1][0] if pos + 1 < len(heading_blocks) else len(blocks)
        content_blocks = blocks[block_index:next_index]

        paragraphs: list[str] = []
        code_examples: list[str] = []
        for block in content_blocks:
            for descr in re.finditer(r'class="t026__descr[^"]*"[^>]*>(.*?)</div>', block, re.S):
                text = clean_text(descr.group(1))
                if text:
                    paragraphs.append(text)
            for text_block in re.finditer(r'class="t-text[^"]*"[^>]*>(.*?)</div>', block, re.S):
                text = clean_text(text_block.group(1))
                if text and text != heading and text not in paragraphs and not is_noise_paragraph(text):
                    paragraphs.append(text)
            for col in re.finditer(r'class="t-col[^"]*"[^>]*>(.*?)</div>\s*</div>', block, re.S):
                text = clean_text(col.group(1))
                if text and len(text) > 20 and text not in paragraphs and not is_noise_paragraph(text):
                    paragraphs.append(text)
            for code in re.finditer(r"<pre[^>]*><code[^>]*>(.*?)</code></pre>", block, re.S):
                code_examples.append(clean_text(code.group(1)))

        sections.append({"heading": heading, "paragraphs": paragraphs, "code_examples": code_examples})

    return sections


def write_overview_md(sections: list[dict], dest: Path) -> None:
    lines = [
        "# Mailganer REST API — обзор",
        "",
        f"Источник: [{DOCS_ROOT}/api/]({DOCS_ROOT}/api/)",
        "",
    ]
    for section in sections:
        lines.append(f"## {section['heading']}")
        lines.append("")
        for paragraph in section.get("paragraphs", []):
            lines.append(paragraph)
            lines.append("")
        for example in section.get("code_examples", []):
            lines.append("```json")
            lines.append(example)
            lines.append("```")
            lines.append("")
    dest.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def parse_endpoint_page(
    html_text: str,
    *,
    path: str,
    menu_title: str,
    category: str,
) -> EndpointPage:
    meta_title = re.search(r"<title>([^<]+)</title>", html_text)
    page_title = clean_text(meta_title.group(1)) if meta_title else menu_title

    methods = sorted(set(re.findall(r"\b(GET|POST|PUT|PATCH|DELETE)\b", html_text)))
    endpoints = []
    for match in re.finditer(r"(GET|POST|PUT|PATCH|DELETE)\s+(https?://[^\s<]+)", html_text):
        endpoint = f"{match.group(1)} {match.group(2)}"
        if endpoint not in endpoints:
            endpoints.append(endpoint)

    headings: list[str] = []
    for match in re.finditer(r'class="t026__title[^"]*"[^>]*>([^<]+)', html_text):
        heading = clean_text(match.group(1))
        if heading and heading not in headings:
            headings.append(heading)

    paragraphs: list[str] = []
    for match in re.finditer(r'class="t026__descr[^"]*"[^>]*>(.*?)</div>', html_text, re.S):
        text = clean_text(match.group(1))
        if text and text not in paragraphs:
            paragraphs.append(text)
    for match in re.finditer(r'class="t-text[^"]*"[^>]*>(.*?)</div>', html_text, re.S):
        text = clean_text(match.group(1))
        if text and text not in paragraphs:
            paragraphs.append(text)

    code_examples: list[dict[str, str]] = []
    for index, match in enumerate(re.finditer(r"<pre[^>]*><code[^>]*>(.*?)</code></pre>", html_text, re.S)):
        code = clean_text(match.group(1))
        if not code:
            continue
        start = max(0, match.start() - 800)
        context = html_text[start : match.start()]
        label_matches = re.findall(r'class="t026__title[^"]*"[^>]*>([^<]+)', context)
        label = clean_text(label_matches[-1]) if label_matches else f"example_{index + 1}"
        code_examples.append({"label": label, "code": code})

    tables: list[list[list[str]]] = []
    for table_block in re.finditer(r'id="rec\d+"[^>]*data-record-type="431".*?(?=<div id="rec|\Z)', html_text, re.S):
        rows: list[list[str]] = []
        for row in re.finditer(r"<tr[^>]*>(.*?)</tr>", table_block.group(0), re.S):
            cells = [
                clean_text(cell.group(1))
                for cell in re.finditer(r"<t[dh][^>]*>(.*?)</t[dh]>", row.group(1), re.S)
            ]
            if any(cells):
                rows.append(cells)
        if rows:
            tables.append(rows)

    return EndpointPage(
        path=path,
        title=page_title,
        category=category,
        url=f"{BASE_URL}{path}",
        http_methods=methods,
        endpoints=endpoints,
        headings=headings,
        paragraphs=paragraphs,
        code_examples=code_examples,
        tables=tables,
        scraped_at=datetime.now(timezone.utc).isoformat(),
    )


def sync_docs(output_dir: Path, delay: float = 0.3) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    endpoints_dir = output_dir / "endpoints"
    endpoints_dir.mkdir(exist_ok=True)

    existing_slugs = {path.stem for path in endpoints_dir.glob("*.json")}

    sitemap_pages: list[dict[str, str]] = []
    sitemap_error: str | None = None
    try:
        sitemap_pages = fetch_sitemap_pages()
        save_sitemap_pages(output_dir, sitemap_pages)
        print(f"Sitemap: {len(sitemap_pages)} documentation page(s)")
    except (urllib.error.URLError, TimeoutError, OSError, ET.ParseError) as exc:
        sitemap_error = str(exc)
        print(f"Sitemap fetch failed, using menu only: {exc}", file=sys.stderr)

    index_html = fetch(f"{BASE_URL}{API_INDEX_PATH}")
    categories = parse_menu(index_html)
    overview_sections = parse_overview_sections(index_html)
    write_overview_md(overview_sections, output_dir / "overview.md")

    flat_items, source_stats = merge_page_sources(sitemap_pages, categories)
    if not flat_items:
        for category, items in categories.items():
            for item in items:
                flat_items.append((category, item, "menu"))
        source_stats = {"from_sitemap": 0, "from_menu": len(flat_items)}

    scraped: list[dict] = []
    failures: list[dict] = []
    new_pages: list[str] = []

    for category, item, page_source in flat_items:
        path = item["path"]
        url = item["url"]
        slug = item["slug"]
        try:
            page_html = fetch(url)
            endpoint = parse_endpoint_page(
                page_html,
                path=path,
                menu_title=item["title"],
                category=category,
            )
            out_file = endpoints_dir / f"{slug}.json"
            out_file.write_text(
                json.dumps(endpoint.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            if slug not in existing_slugs:
                new_pages.append(slug)
            scraped.append(
                {
                    "slug": slug,
                    "path": path,
                    "title": endpoint.title,
                    "category": category,
                    "source": page_source,
                    "endpoints": endpoint.endpoints,
                    "file": str(out_file.relative_to(output_dir)),
                }
            )
            marker = " (new)" if slug in new_pages else ""
            print(f"✓ {slug}: {endpoint.title}{marker}")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            failures.append({"path": path, "url": url, "error": str(exc)})
            print(f"✗ {slug}: {exc}", file=sys.stderr)
        time.sleep(delay)

    api_index = {
        "sources": {
            "primary": SITEMAP_URL,
            "fallback": f"{BASE_URL}{API_INDEX_PATH}",
            "postman": "https://documenter.getpostman.com/view/23131434/VUxPvnhA",
        },
        "source": f"{BASE_URL}{API_INDEX_PATH}",
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "base_api_url": "https://mailganer.com/api/",
        "auth": {
            "v1": "api_key in request body",
            "v2": "Authorization: CodeRequest {{api_key}} header",
        },
        "rate_limit": "500 requests per minute (HTTP 429 on exceed)",
        "pagination": {
            "page_size": 25,
            "fields": ["count", "results", "next", "previous"],
        },
        "categories": categories,
        "endpoints": scraped,
        "failures": failures,
        "sitemap": {
            "url": SITEMAP_URL,
            "pages_total": len(sitemap_pages),
            "error": sitemap_error,
            "file": "sitemap-pages.json",
        },
        "stats": {
            "categories": len(categories),
            "pages_total": len(flat_items),
            "pages_scraped": len(scraped),
            "pages_failed": len(failures),
            "pages_from_sitemap": source_stats["from_sitemap"],
            "pages_from_menu": source_stats["from_menu"],
            "pages_new": len(new_pages),
            "pages_previously_scraped": len(existing_slugs),
        },
    }
    (output_dir / "api-index.json").write_text(
        json.dumps(api_index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return api_index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "docs",
        help="Output directory for cached docs (default: docs/)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.3,
        help="Delay between HTTP requests in seconds",
    )
    args = parser.parse_args()

    result = sync_docs(args.output, delay=args.delay)
    stats = result["stats"]
    print(
        f"\nDone: {stats['pages_scraped']}/{stats['pages_total']} pages "
        f"(sitemap {stats['pages_from_sitemap']}, menu {stats['pages_from_menu']}, "
        f"new {stats['pages_new']}, was {stats['pages_previously_scraped']}), "
        f"{stats['categories']} categories, {stats['pages_failed']} failures"
    )
    return 1 if stats["pages_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
