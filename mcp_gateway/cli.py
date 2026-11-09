#!/usr/bin/env python3
"""CLI for mcp-gateway-governance-kit.

    catalog                         list servers, tools, required scopes
    policy [--role R]               the one policy table (scopes derived)
    check                           governance findings; exit 0 clean /
                                    1 findings present / 2 data error
    grants [--role R]               actual grants vs needs, expanded
    diff --person NAME              joiner/mover/leaver diff for a person
    diff --from R --to R            ...or for an ad-hoc role change
    evidence [--out DIR]            write evidence_pack.json + summary .md
    verify --pack FILE              verify an evidence pack offline
    demo                            end-to-end scripted scenario
    serve [--port N]                JSON API on 127.0.0.1
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_gateway import demo as demo_mod  # noqa: E402
from mcp_gateway.catalog import load_catalog_file  # noqa: E402
from mcp_gateway.checks import run_checks  # noqa: E402
from mcp_gateway.diff import diff_access, diff_person  # noqa: E402
from mcp_gateway.evidence import build_pack, render_markdown, verify_pack  # noqa: E402
from mcp_gateway.policy import (  # noqa: E402
    load_grants_file, load_people_file, load_policy_file,
)
from mcp_gateway import scopes as scope_logic  # noqa: E402
from mcp_gateway.server import serve  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "fixtures")


def _load(catalog_path, policy_path, grants_path, people_path):
    return (load_catalog_file(catalog_path), load_policy_file(policy_path),
            load_grants_file(grants_path), load_people_file(people_path))


def _defaults(p: argparse.ArgumentParser) -> None:
    p.add_argument("--catalog", default=os.path.join(FIXTURES, "catalog.json"))
    p.add_argument("--policy", default=os.path.join(FIXTURES, "policy.json"))
    p.add_argument("--grants", default=os.path.join(FIXTURES, "grants.json"))
    p.add_argument("--people", default=os.path.join(FIXTURES, "people.json"))


def cmd_catalog(a) -> int:
    catalog, _, _, _ = _load(a.catalog, a.policy, a.grants, a.people)
    for s in catalog.servers:
        print(f"{s.id} ({s.name})")
        for t in s.tools:
            print(f"  {t.id:28} scopes={','.join(t.scopes)} "
                  f"action={t.action} resource={t.resource}")
    print(f"universe: {len(catalog.universe_scopes())} scopes, "
          f"{len(catalog.all_tools())} tools, {len(catalog.servers)} servers")
    return 0


def cmd_policy(a) -> int:
    catalog, policy, _, _ = _load(a.catalog, a.policy, a.grants, a.people)
    roles = [a.role] if a.role else policy.role_names()
    for role in roles:
        print(f"{role}:")
        for srv in policy.allowed_servers(role):
            tools = ", ".join(policy.roles[role][srv])
            print(f"  {srv}: {tools}")
        print(f"  scopes (derived): {', '.join(policy.required_scopes(catalog, role))}")
    return 0


def cmd_check(a) -> int:
    catalog, policy, grants, _ = _load(a.catalog, a.policy, a.grants, a.people)
    problems = catalog.validate() + policy.validate(catalog)
    if problems:
        for p in problems:
            print(f"[ERROR] {p}")
        return 2
    checks = run_checks(catalog, policy, grants)
    for f in checks["grant_findings"]:
        print(f"[{f['type']}] {f['id']}: {f['message']}")
    for f in checks["sod_findings"]:
        print(f"[{f['type']}] {f['id']}: {f['message']}")
    gaps = {r: g for r, g in checks["coverage_gaps"].items() if g}
    for role, missing in sorted(gaps.items()):
        print(f"[COVERAGE_GAP] {role}: missing {', '.join(missing)}")
    s = checks["summary"]
    print(f"summary: {s['total_findings']} findings "
          f"({s['grant_findings']} grant, {s['sod_findings']} SoD) over "
          f"{checks['grants_examined']} grants; "
          f"{s['roles_with_gaps']} roles with coverage gaps")
    return 1 if s["total_findings"] or gaps else 0


def cmd_grants(a) -> int:
    catalog, policy, grants, _ = _load(a.catalog, a.policy, a.grants, a.people)
    universe = catalog.universe_scopes()
    roles = [a.role] if a.role else sorted(grants)
    for role in roles:
        granted = grants[role]
        expanded = scope_logic.expand(granted, universe)
        print(f"{role}: granted={', '.join(granted)}")
        print(f"  expanded via implication: {', '.join(expanded)}")
        print(f"  needed by policy tools:   "
              f"{', '.join(policy.required_scopes(catalog, role))}")
    return 0


def cmd_diff(a) -> int:
    catalog, policy, grants, people = _load(a.catalog, a.policy, a.grants,
                                            a.people)
    if a.person:
        person = next((p for p in people if p["name"] == a.person), None)
        if person is None:
            print(f"error: unknown person {a.person!r}", file=sys.stderr)
            return 2
        d = diff_person(catalog, policy, grants, person)
    else:
        d = diff_access(catalog, policy, grants, a.from_role, a.to_role)
    print(json.dumps(d, indent=2, sort_keys=True))
    return 0


def cmd_evidence(a) -> int:
    catalog, policy, grants, people = _load(a.catalog, a.policy, a.grants,
                                            a.people)
    pack = build_pack(catalog, policy, grants, people)
    os.makedirs(a.out, exist_ok=True)
    pack_path = os.path.join(a.out, "evidence_pack.json")
    with open(pack_path, "w", encoding="utf-8") as f:
        json.dump(pack, f, indent=2, sort_keys=True)
        f.write("\n")
    md_path = os.path.join(a.out, "evidence_summary.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(pack))
    print(f"evidence pack: {pack_path}")
    print(f"summary:       {md_path}")
    print(f"audit chain:   {pack['audit_chain']['message']}")
    return 0


def cmd_verify(a) -> int:
    catalog, policy, grants, people = _load(a.catalog, a.policy, a.grants,
                                            a.people)
    with open(a.pack, encoding="utf-8") as f:
        pack = json.load(f)
    ok, msg = verify_pack(pack, catalog, policy, grants, people)
    print(msg)
    return 0 if ok else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mcp-gateway-governance")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("demo"); _defaults(s)
    s.set_defaults(fn=lambda a: demo_mod.run() or 0)
    s = sub.add_parser("catalog"); _defaults(s); s.set_defaults(fn=cmd_catalog)
    s = sub.add_parser("policy"); _defaults(s)
    s.add_argument("--role"); s.set_defaults(fn=cmd_policy)
    s = sub.add_parser("check"); _defaults(s); s.set_defaults(fn=cmd_check)
    s = sub.add_parser("grants"); _defaults(s)
    s.add_argument("--role"); s.set_defaults(fn=cmd_grants)
    s = sub.add_parser("diff"); _defaults(s)
    s.add_argument("--person")
    s.add_argument("--from", dest="from_role")
    s.add_argument("--to", dest="to_role")
    s.set_defaults(fn=cmd_diff)
    s = sub.add_parser("evidence"); _defaults(s)
    s.add_argument("--out", default=os.path.join(ROOT, "var", "evidence"))
    s.set_defaults(fn=cmd_evidence)
    s = sub.add_parser("verify"); _defaults(s)
    s.add_argument("--pack", required=True); s.set_defaults(fn=cmd_verify)
    s = sub.add_parser("serve"); _defaults(s)
    s.add_argument("--port", type=int, default=8473)
    s.set_defaults(fn=lambda a: serve(*_load(a.catalog, a.policy, a.grants,
                                             a.people), a.port) or 0)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
