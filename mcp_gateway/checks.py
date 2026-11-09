"""Governance checks: over-broad grants and segregation of duties.

Over-broad detection is defined entirely by the scope-implication graph
(scopes.py): each grant is expanded against the catalog universe and
compared with what the role's tools actually require.

    WILDCARD_GRANT   a wildcard grant (crm:*) — flagged on sight, because
                     it also confers every FUTURE scope under the prefix;
                     `excess` lists what it over-covers today.
    UNUSED_GRANT     the grant's expansion overlaps nothing the role
                     needs — access nobody's tools can justify.
    IMPLIED_EXCESS   the grant covers a need but drags in unneeded power
                     with it (classic case: billing:payments:write held
                     when only the implied read is ever used).

Segregation of duties is a policy-level check (independent of grants):
a role whose allowed tools can both CREATE and APPROVE the same resource
class can push its own work through — a SOX-style conflict.
"""

from __future__ import annotations

from . import scopes as scope_logic
from .catalog import Catalog
from .policy import Policy


def grant_findings(catalog: Catalog, policy: Policy, grants: dict) -> list[dict]:
    """One finding per offending grant, sorted by finding id."""
    universe = catalog.universe_scopes()
    findings: list[dict] = []
    for role in sorted(grants):
        required = set(policy.required_scopes(catalog, role))
        for granted in grants[role]:
            implied = set(scope_logic.expand([granted], universe))
            excess = sorted(implied - required)
            if "*" in granted:
                ftype = "WILDCARD_GRANT"
                msg = (f"wildcard grant {granted!r} confers {sorted(implied)}; "
                       f"role needs only {sorted(implied & required)} of them, "
                       f"and every future scope under the prefix arrives silently")
            elif not (implied & required):
                ftype = "UNUSED_GRANT"
                msg = (f"grant {granted!r} confers {sorted(implied)}, none of "
                       f"which any tool allowed for role {role!r} requires")
            elif excess:
                ftype = "IMPLIED_EXCESS"
                msg = (f"grant {granted!r} covers a real need but also confers "
                       f"unneeded {excess} via scope implication")
            else:
                continue
            findings.append({
                "id": f"{ftype}:{role}:{granted}",
                "type": ftype,
                "role": role,
                "scope": granted,
                "excess": excess,
                "message": msg,
            })
    return sorted(findings, key=lambda f: f["id"])


def sod_findings(catalog: Catalog, policy: Policy) -> list[dict]:
    """Create+approve on the same resource class within one role."""
    findings: list[dict] = []
    for role in policy.role_names():
        by_resource: dict[str, dict[str, list[str]]] = {}
        for tid in policy.allowed_tool_ids(role):
            tool = catalog.tool_by_id(tid)
            if tool.action in ("create", "approve"):
                by_resource.setdefault(tool.resource, {}).setdefault(
                    tool.action, []).append(tid)
        for resource in sorted(by_resource):
            acts = by_resource[resource]
            if "create" in acts and "approve" in acts:
                creates = sorted(acts["create"])
                approves = sorted(acts["approve"])
                findings.append({
                    "id": f"SOD:{role}:{resource}:"
                          f"{'+'.join(creates)}+{'+'.join(approves)}",
                    "type": "SOD_CONFLICT",
                    "role": role,
                    "resource": resource,
                    "create_tools": creates,
                    "approve_tools": approves,
                    "message": (f"role {role!r} can both create ({creates}) and "
                                f"approve ({approves}) {resource} — the same "
                                f"person can push their own work through"),
                })
    return sorted(findings, key=lambda f: f["id"])


def coverage_gaps(catalog: Catalog, policy: Policy, grants: dict) -> dict:
    """Required scopes no grant confers, per role ({} values omitted upstream
    only when empty everywhere — callers get every role's list, possibly [])."""
    gaps: dict[str, list[str]] = {}
    for role in policy.role_names():
        granted = grants.get(role, [])
        missing = [sc for sc in policy.required_scopes(catalog, role)
                   if not scope_logic.covers(granted, sc)]
        gaps[role] = missing
    return gaps


def run_checks(catalog: Catalog, policy: Policy, grants: dict) -> dict:
    """All governance checks in one deterministic bundle."""
    gf = grant_findings(catalog, policy, grants)
    sf = sod_findings(catalog, policy)
    gaps = coverage_gaps(catalog, policy, grants)
    by_type: dict[str, int] = {}
    for f in gf:
        by_type[f["type"]] = by_type.get(f["type"], 0) + 1
    return {
        "grant_findings": gf,
        "sod_findings": sf,
        "coverage_gaps": gaps,
        "grants_examined": sum(len(v) for v in grants.values()),
        "summary": {
            "grant_findings": len(gf),
            "grant_findings_by_type": by_type,
            "sod_findings": len(sf),
            "roles_with_gaps": sum(1 for v in gaps.values() if v),
            "total_findings": len(gf) + len(sf),
        },
    }
