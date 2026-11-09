"""Joiner / mover / leaver simulator — where access creep becomes visible.

The policy diff (gained/lost) is what SHOULD change when a person changes
roles. Creep is what ACTUALLY stays behind if their old grants are simply
kept: the old role's real grants are expanded through the implication
graph, and whatever the new role does not need — plus every tool those
retained grants still make usable, including tools the person was never
assigned — is reported as creep.

    mover    creep = (old grants, expanded) − (new role's needs), and
             usable-with-old-grants tools − new role's allowed tools
    joiner   creep = the new role's grants beyond its own policy
             (over-provisioning on day one)
    leaver   creep = everything the old grants still make usable —
             the residual access that must be revoked, in full
"""

from __future__ import annotations

from . import scopes as scope_logic
from .catalog import Catalog
from .policy import Policy


def usable_tools(catalog: Catalog, granted: list[str]) -> list[str]:
    """Tools whose every required scope is conferred by the grants."""
    return sorted(t.id for t in catalog.all_tools()
                  if all(scope_logic.covers(granted, sc) for sc in t.scopes))


def diff_access(catalog: Catalog, policy: Policy, grants: dict,
                from_role: str | None, to_role: str | None) -> dict:
    """Exact access diff for a role change. Either role may be None
    (joiner: from None; leaver: to None)."""
    old_tools = set(policy.allowed_tool_ids(from_role)) if from_role else set()
    new_tools = set(policy.allowed_tool_ids(to_role)) if to_role else set()
    old_scopes = (set(policy.required_scopes(catalog, from_role))
                  if from_role else set())
    new_scopes = (set(policy.required_scopes(catalog, to_role))
                  if to_role else set())
    universe = catalog.universe_scopes()

    if from_role is not None:
        # What the person actually holds today (their current role's grants).
        held = grants.get(from_role, [])
        held_expanded = set(scope_logic.expand(held, universe))
        creep_scopes = sorted(held_expanded - new_scopes)
        creep_tools = sorted(set(usable_tools(catalog, held)) - new_tools)
    else:
        # Joiner: creep is over-provisioning inside the new role's own grants.
        held = grants.get(to_role, [])
        held_expanded = set(scope_logic.expand(held, universe))
        creep_scopes = sorted(held_expanded - new_scopes)
        creep_tools = sorted(set(usable_tools(catalog, held)) - new_tools)

    if from_role is None:
        kind = "joiner"
    elif to_role is None:
        kind = "leaver"
    else:
        kind = "mover"
    return {
        "kind": kind,
        "from_role": from_role,
        "to_role": to_role,
        "gained_tools": sorted(new_tools - old_tools),
        "lost_tools": sorted(old_tools - new_tools),
        "gained_scopes": sorted(new_scopes - old_scopes),
        "lost_scopes": sorted(old_scopes - new_scopes),
        "creep_tools": creep_tools,
        "creep_scopes": creep_scopes,
    }


def diff_person(catalog: Catalog, policy: Policy, grants: dict,
                person: dict) -> dict:
    """diff_access for one fixtures/people.json entry, named."""
    d = diff_access(catalog, policy, grants,
                    person.get("from_role"), person.get("to_role"))
    return {"person": person["name"], **d}
