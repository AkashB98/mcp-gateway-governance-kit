"""The ONE policy model: role -> allowed servers -> allowed tools.

There is deliberately no separate scope table, server table, and tool
table to drift apart. A role's allowed scopes are DERIVED from its
allowed tools via the catalog: the scopes a role needs are exactly the
scopes its tools require. Grants (what the identity provider actually
issued) live in a separate file — governance is the comparison between
this model (should-have) and the grants (do-have).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .catalog import Catalog


@dataclass
class Policy:
    name: str = ""
    # role -> {server_id -> [tool_name, ...]}  (the single table)
    roles: dict = field(default_factory=dict)

    def role_names(self) -> list[str]:
        return sorted(self.roles)

    def allowed_tool_ids(self, role: str) -> list[str]:
        if role not in self.roles:
            raise KeyError(f"unknown role {role!r}")
        return sorted(f"{srv}.{tool}"
                      for srv, tools in self.roles[role].items()
                      for tool in tools)

    def allowed_servers(self, role: str) -> list[str]:
        if role not in self.roles:
            raise KeyError(f"unknown role {role!r}")
        return sorted(self.roles[role])

    def required_scopes(self, catalog: Catalog, role: str) -> list[str]:
        """Scopes this role needs = union of its tools' required scopes."""
        return sorted({sc for tid in self.allowed_tool_ids(role)
                       for sc in catalog.tool_by_id(tid).scopes})

    def validate(self, catalog: Catalog) -> list[str]:
        """Policy references that don't resolve against the catalog."""
        problems: list[str] = []
        known_servers = set(catalog.server_ids())
        for role, servers in sorted(self.roles.items()):
            for srv, tools in sorted(servers.items()):
                if srv not in known_servers:
                    problems.append(f"role {role!r} allows unknown server {srv!r}")
                    continue
                known_tools = {t.name for s in catalog.servers if s.id == srv
                               for t in s.tools}
                for tool in tools:
                    if tool not in known_tools:
                        problems.append(
                            f"role {role!r} allows unknown tool {srv}.{tool}")
        return problems


def load_policy(d: dict) -> Policy:
    return Policy(name=d.get("name", ""), roles=d.get("roles", {}))


def load_policy_file(path: str) -> Policy:
    with open(path, encoding="utf-8") as f:
        return load_policy(json.load(f))


def load_grants(d: dict) -> dict:
    """role -> sorted list of actually-granted scope strings."""
    return {role: sorted(scopes) for role, scopes in d.get("grants", {}).items()}


def load_grants_file(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return load_grants(json.load(f))


def load_people(d: dict) -> list[dict]:
    """[{name, from_role|None, to_role|None, kind}] sorted by name."""
    return sorted(d.get("people", []), key=lambda p: p["name"])


def load_people_file(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return load_people(json.load(f))
