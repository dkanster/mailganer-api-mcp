"""Mailganer API documentation MCP server."""

from __future__ import annotations

import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

import docs_kb

server = Server("mailganer-api")


def _json(data: object) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, ensure_ascii=False, indent=2))]


def _text(data: str) -> list[TextContent]:
    return [TextContent(type="text", text=data)]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_doc_status",
            description="Get sync status of cached Mailganer API docs and Postman collection",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="sync_documentation",
            description="Re-sync Mailganer API documentation from web sources into docs/",
            inputSchema={
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "enum": ["all", "api", "postman"],
                        "default": "all",
                        "description": "What to sync: all sources, API pages only, or Postman only",
                    }
                },
            },
        ),
        Tool(
            name="list_api_docs",
            description="List cached Mailganer API documentation pages, optionally by category",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Filter by category, e.g. подписчик or триггер",
                    }
                },
            },
        ),
        Tool(
            name="search_api_docs",
            description="Full-text search in cached Mailganer API documentation",
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
            description="Get cached Mailganer API doc page with linked Postman requests",
            inputSchema={
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "Page slug, e.g. email-add or trigger-send-v2",
                    }
                },
                "required": ["slug"],
            },
        ),
        Tool(
            name="get_linked_postman_request",
            description="Get Postman request with related Mailganer documentation pages",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Partial Postman request name"},
                    "path": {"type": "string", "description": "API path, e.g. /api/v2/emails/"},
                },
            },
        ),
        Tool(
            name="check_doc_page",
            description="Compare a cached doc page with the live site and report differences",
            inputSchema={
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "Page slug to check against live documentation",
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
        Tool(
            name="search_postman",
            description="Search Mailganer Postman collection requests by keyword",
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
            name="get_postman_request",
            description="Get a Postman request by partial name or exact API path (without related docs)",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Partial request name"},
                    "path": {"type": "string", "description": "API path, e.g. /api/v2/emails/"},
                },
            },
        ),
        Tool(
            name="rebuild_doc_crosslinks",
            description="Rebuild docs ↔ Postman crosslink index in docs/crosslinks.json",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="list_crosslink_gaps",
            description="List docs and Postman requests without crosslinks, with documented reasons",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "get_doc_status":
        return _json(docs_kb.get_doc_status())

    if name == "sync_documentation":
        target = arguments.get("target", "all")
        return _json(docs_kb.sync_documentation(target=target))

    if name == "list_api_docs":
        return _json(docs_kb.list_api_docs(category=arguments.get("category")))

    if name == "search_api_docs":
        return _json(
            docs_kb.search_api_docs(
                arguments["query"],
                limit=int(arguments.get("limit", 10)),
            )
        )

    if name == "get_api_endpoint_doc":
        return _json(docs_kb.get_linked_endpoint_doc(arguments["slug"]))

    if name == "get_linked_postman_request":
        return _json(
            docs_kb.get_linked_postman_request(
                name=arguments.get("name"),
                path=arguments.get("path"),
            )
        )

    if name == "check_doc_page":
        return _json(docs_kb.check_doc_page(arguments["slug"]))

    if name == "get_api_overview":
        overview = docs_kb.DOCS_DIR / "overview.md"
        if overview.exists():
            return _text(overview.read_text(encoding="utf-8"))
        return _text("Overview not found. Run sync_documentation first.")

    if name == "search_postman":
        return _json(
            docs_kb.search_postman(
                arguments["query"],
                limit=int(arguments.get("limit", 10)),
            )
        )

    if name == "get_postman_request":
        item = docs_kb.get_postman_request(
            name=arguments.get("name"),
            path=arguments.get("path"),
        )
        if item is None:
            return _text("Postman request not found")
        return _json(item)

    if name == "rebuild_doc_crosslinks":
        return _json(docs_kb.build_crosslinks(save=True))

    if name == "list_crosslink_gaps":
        return _json(docs_kb.list_crosslink_gaps())

    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main_sync() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
