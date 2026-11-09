"""Audit evidence: one JSON evidence pack + a Markdown summary.

An auditor (or a hiring manager) should be able to check the governance
claims OFFLINE, without trusting the tool that produced them. So:

    build_pack()   runs every check and every person's role-change diff,
                   records each step in the hash-chained audit log, and
                   embeds the records in the pack.
    verify_pack()  recomputes everything from the catalog/policy/grants/
                   people inputs and compares it field-by-field with the
                   pack, then re-verifies the embedded hash chain. Any
                   edited finding, count, or audit record fails.
    render_markdown() derives the human summary FROM the pack — the .md
                   is a view, never a second source of truth.
"""

from __future__ import annotations

import os
import tempfile
import time
from typing import Callable

from .audit import AuditLog, verify_records
from .catalog import Catalog
from .checks import run_checks
from .diff import diff_person
from .policy import Policy

PACK_VERSION = 1


class _StepClock:
    """Deterministic clock for pack building: start, then +1s per call."""

    def __init__(self, start: float = 1_700_000_000.0):
        self.t = start

    def __call__(self) -> float:
        self.t += 1
        return self.t


def build_pack(catalog: Catalog, policy: Policy, grants: dict,
               people: list[dict],
               clock: Callable[[], float] | None = None) -> dict:
    clock = clock or _StepClock()
    audit_path = tempfile.mktemp(suffix=".jsonl")
    audit = AuditLog(audit_path, clock=clock)
    try:
        audit.append("catalog_loaded",
                     servers=len(catalog.servers),
                     tools=len(catalog.all_tools()),
                     universe_scopes=len(catalog.universe_scopes()))
        checks = run_checks(catalog, policy, grants)
        audit.append("checks_completed",
                     grant_findings=checks["summary"]["grant_findings"],
                     sod_findings=checks["summary"]["sod_findings"],
                     total_findings=checks["summary"]["total_findings"])
        diffs = []
        for person in people:
            d = diff_person(catalog, policy, grants, person)
            diffs.append(d)
            audit.append("diff_computed", person=person["name"], kind=d["kind"],
                         creep_tools=len(d["creep_tools"]),
                         creep_scopes=len(d["creep_scopes"]))
        audit.append("evidence_sealed", pack_version=PACK_VERSION)
        records = audit.read_all()
    finally:
        if os.path.exists(audit_path):
            os.remove(audit_path)
    ok, msg = verify_records(records)
    return {
        "pack_version": PACK_VERSION,
        "catalog": {
            "name": catalog.name,
            "servers": len(catalog.servers),
            "tools": len(catalog.all_tools()),
            "universe_scopes": catalog.universe_scopes(),
        },
        "roles": policy.role_names(),
        "grants_examined": checks["grants_examined"],
        "grant_findings": checks["grant_findings"],
        "sod_findings": checks["sod_findings"],
        "coverage_gaps": checks["coverage_gaps"],
        "diffs": diffs,
        "summary": checks["summary"],
        "audit_records": records,
        "audit_chain": {"valid": ok, "message": msg},
    }


def verify_pack(pack: dict, catalog: Catalog, policy: Policy, grants: dict,
                people: list[dict]) -> tuple[bool, str]:
    """Offline verification: recompute from inputs, compare, check chain."""
    ok, msg = verify_records(pack.get("audit_records", []))
    if not ok:
        return False, f"audit chain: {msg}"
    fresh = build_pack(catalog, policy, grants, people)
    # Timestamps inside audit records legitimately differ between builds;
    # everything else — findings, diffs, counts, the chain's event shape —
    # must match exactly.
    def _shape(p):
        return {
            "catalog": p["catalog"],
            "roles": p["roles"],
            "grants_examined": p["grants_examined"],
            "grant_findings": p["grant_findings"],
            "sod_findings": p["sod_findings"],
            "coverage_gaps": p["coverage_gaps"],
            "diffs": p["diffs"],
            "summary": p["summary"],
            "audit_events": [(r["seq"], r["event"]) for r in p["audit_records"]],
        }
    if _shape(pack) != _shape(fresh):
        return False, "pack contents do not match a fresh recomputation"
    return True, ("pack verified: findings, diffs and counts match a fresh "
                  "recomputation; " + msg)


def render_markdown(pack: dict) -> str:
    """Short human summary rendered from the pack (never hand-written)."""
    s = pack["summary"]
    lines = [
        "# MCP gateway governance — evidence summary",
        "",
        f"- Catalog: {pack['catalog']['servers']} servers, "
        f"{pack['catalog']['tools']} tools, "
        f"{len(pack['catalog']['universe_scopes'])} scopes in universe",
        f"- Grants examined: {pack['grants_examined']}",
        f"- Grant findings: {s['grant_findings']} "
        f"({', '.join(f'{k}={v}' for k, v in sorted(s['grant_findings_by_type'].items()))})",
        f"- Segregation-of-duties conflicts: {s['sod_findings']}",
        f"- Roles with coverage gaps: {s['roles_with_gaps']}",
        f"- Audit chain: {pack['audit_chain']['message']} "
        f"(valid: {pack['audit_chain']['valid']})",
        "",
        "## Grant findings",
        "",
    ]
    for f in pack["grant_findings"]:
        lines.append(f"- `{f['id']}` — excess: "
                     f"{', '.join(f['excess']) if f['excess'] else '(none today; future scopes under the prefix arrive silently)'}")
    lines += ["", "## Segregation of duties", ""]
    for f in pack["sod_findings"]:
        lines.append(f"- `{f['id']}` — {f['message']}")
    lines += ["", "## Role changes: access creep if old grants are kept", ""]
    for d in pack["diffs"]:
        lines.append(
            f"- {d['person']} ({d['kind']}: {d['from_role'] or '—'} → "
            f"{d['to_role'] or '—'}): gained {len(d['gained_tools'])} tools / "
            f"{len(d['gained_scopes'])} scopes; creep "
            f"{len(d['creep_tools'])} tools / {len(d['creep_scopes'])} scopes"
            + (f" — creep tools: {', '.join(d['creep_tools'])}"
               if d["creep_tools"] else ""))
    lines.append("")
    return "\n".join(lines)
