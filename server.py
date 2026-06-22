"""Mailganer API MCP server (stub — knowledge base first)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

DOCS_DIR = Path(__file__).resolve().parent / "docs"
INDEX_FILE = DOCS_DIR / "api-index.json"

server = Server("mailganer-api")


def load_index() -> dict:
    if not INDEX_FILE.exists():
        return {"endpoints": [], "categories": {}}
    return json.loads(INDEX_FILE.read_text(encoding="utf-8"))


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_api_docs",
            description="Search cached Mailganer REST API documentation by keyword",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_api_endpoint_doc",
            description="Get full cached documentation for a Mailganer API endpoint by slug",
            inputSchema={
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "Endpoint slug, e.g. email-add or trigger-send-v2",
                    }
                },
                "required": ["slug"],
            },
        ),
        Tool(
            name="get_api_overview",
            description="Get Mailganer API overview: auth, limits, pagination",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "get_api_overview":
        overview = DOCS_DIR / "overview.md"
        if overview.exists():
            return [TextContent(type="text", text=overview.read_text(encoding="utf-8"))]
        return [TextContent(type="text", text="Overview not found. Run scripts/sync-api-docs.py first.")]

    if name == "get_api_endpoint_doc":
        slug = arguments["slug"]
        path = DOCS_DIR / "endpoints" / f"{slug}.json"
        if not path.exists():
            return [TextContent(type="text", text=f"Endpoint doc not found: {slug}")]
        return [TextContent(type="text", text=path.read_text(encoding="utf-8"))]

    if name == "search_api_docs":
        query = arguments["query"].lower()
        limit = int(arguments.get("limit", 10))
        index = load_index()
        matches = []
        for item in index.get("endpoints", []):
            haystack = " ".join(
                [
                    item.get("title", ""),
                    item.get("path", ""),
                    item.get("category", ""),
                    " ".join(item.get("endpoints", [])),
                ]
            ).lower()
            if query in haystack:
                matches.append(item)
            if len(matches) >= limit:
                break
        return [TextContent(type="text", text=json.dumps(matches, ensure_ascii=False, indent=2))]

    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main_sync() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
