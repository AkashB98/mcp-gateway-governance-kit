"""MCP catalog: the registry of servers, their tools, and required scopes.

A catalog is data, not code: fictional MCP servers declare their tools,
the OAuth scopes each tool requires, and — for segregation-of-duties
checks — the tool's action (read/create/approve/write/export) and the
resource class it acts on (invoices, pull_requests, ...).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

ACTIONS = ("read", "create", "approve", "write", "export")


@dataclass
class Tool:
    server: str
    name: str
    scopes: tuple = ()
    action: str = "read"
    resource: str = ""

    @property
    def id(self) -> str:
        return f"{self.server}.{self.name}"


@dataclass
class Server:
    id: str
    name: str = ""
    tools: list = field(default_factory=list)  # list[Tool]


@dataclass
class Catalog:
    name: str = ""
    servers: list = field(default_factory=list)  # list[Server]

    def server_ids(self) -> list[str]:
        return sorted(s.id for s in self.servers)

    def all_tools(self) -> list[Tool]:
        return [t for s in self.servers for t in s.tools]

    def tool_ids(self) -> list[str]:
        return sorted(t.id for t in self.all_tools())

    def tool_by_id(self, tool_id: str) -> Tool:
        for t in self.all_tools():
            if t.id == tool_id:
                return t
        raise KeyError(f"unknown tool {tool_id!r}")

    def universe_scopes(self) -> list[str]:
        """Every scope any tool requires — the finite world grants expand into."""
        return sorted({sc for t in self.all_tools() for sc in t.scopes})

    def validate(self) -> list[str]:
        """Structural problems in the catalog itself (empty list = clean)."""
        problems: list[str] = []
        seen_servers: set[str] = set()
        for s in self.servers:
            if s.id in seen_servers:
                problems.append(f"duplicate server id {s.id!r}")
            seen_servers.add(s.id)
            seen_tools: set[str] = set()
            for t in s.tools:
                if t.name in seen_tools:
                    problems.append(f"duplicate tool {t.id!r}")
                seen_tools.add(t.name)
                if t.server != s.id:
                    problems.append(f"tool {t.id!r} filed under server {s.id!r}")
                if not t.scopes:
                    problems.append(f"tool {t.id!r} requires no scopes")
                if t.action not in ACTIONS:
                    problems.append(f"tool {t.id!r} has unknown action {t.action!r}")
                if not t.resource:
                    problems.append(f"tool {t.id!r} has no resource class")
        return problems


def load_catalog(d: dict) -> Catalog:
    servers = []
    for s in d.get("servers", []):
        tools = [Tool(server=s["id"], name=t["name"],
                      scopes=tuple(t.get("scopes", [])),
                      action=t.get("action", "read"),
                      resource=t.get("resource", ""))
                 for t in s.get("tools", [])]
        servers.append(Server(id=s["id"], name=s.get("name", ""), tools=tools))
    return Catalog(name=d.get("name", ""), servers=servers)


def load_catalog_file(path: str) -> Catalog:
    with open(path, encoding="utf-8") as f:
        return load_catalog(json.load(f))
