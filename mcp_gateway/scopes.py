"""Scope-implication reasoning: the logic core of the governance checks.

A granted scope rarely means exactly one permission. This module models
what a grant ACTUALLY confers, as a relation over scope strings:

    exact          crm:contacts:read  implies itself
    global         *                  implies everything
    wildcard       crm:*              implies every scope under crm:
    parent         crm:contacts       implies crm:contacts:read (children)
                   crm                implies every crm:... scope
    verb downgrade (same resource prefix, last segment is the verb)
                   ...:admin          implies ...:write, ...:read, ...:approve
                   ...:write          implies ...:read
                   ...:approve        implies ...:read

`export` is deliberately NOT part of the verb ladder: holding write access
to a resource must not silently confer bulk-export rights.

The relation is evaluated directly (the rules above are already closed
under transitivity for these forms: a parent of a write scope reaches the
read scope via the parent rule, an admin reaches read via the ladder), and
`expand()` materialises it against a finite universe — here, every scope
any catalog tool requires. Over-broad detection in checks.py is defined
entirely in terms of this expansion: a grant is only "needed" to the
extent its expansion overlaps what the role's tools require.
"""

from __future__ import annotations

_VERB_RANK = {"read": 0, "write": 1, "admin": 2}
_KNOWN_VERBS = {"read", "write", "approve", "admin", "export"}


def _split_verb(scope: str) -> tuple[str, str | None]:
    """Split 'a:b:write' -> ('a:b', 'write'); no known verb -> (scope, None)."""
    parts = scope.split(":")
    if len(parts) >= 2 and parts[-1] in _KNOWN_VERBS:
        return ":".join(parts[:-1]), parts[-1]
    return scope, None


def implies(granted: str, candidate: str) -> bool:
    """True when holding `granted` necessarily confers `candidate`."""
    if granted == candidate:
        return True
    if granted == "*":
        return True
    # Wildcard: crm:* -> prefix 'crm:' covers every scope under it.
    if granted.endswith(":*"):
        return candidate.startswith(granted[:-1])
    # Parent scope implies child scopes: crm -> crm:contacts:read.
    if candidate.startswith(granted + ":"):
        return True
    # Verb ladder on the same resource prefix.
    g_res, g_verb = _split_verb(granted)
    c_res, c_verb = _split_verb(candidate)
    if g_verb is not None and c_verb is not None and g_res == c_res:
        if g_verb == "admin" and c_verb in ("write", "read", "approve"):
            return True
        if g_verb in _VERB_RANK and c_verb in _VERB_RANK:
            return _VERB_RANK[g_verb] >= _VERB_RANK[c_verb]
        if g_verb == "approve" and c_verb == "read":
            return True
    return False


def expand(granted: list[str], universe: list[str]) -> list[str]:
    """Every universe scope conferred by any of the granted scopes, sorted."""
    return sorted({u for u in universe if any(implies(g, u) for g in granted)})


def covers(granted: list[str], required_scope: str) -> bool:
    """True when the granted set confers one required scope."""
    return any(implies(g, required_scope) for g in granted)
