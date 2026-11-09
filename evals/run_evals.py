#!/usr/bin/env python3
"""Golden evals for mcp-gateway-governance-kit.

Deterministic scenarios with PINNED expectations (evals/golden.json):
catalog shape, the implication graph, exact over-broad finding ids,
exact segregation-of-duties ids, coverage gaps, the five seeded
joiner/mover/leaver diffs (creep lists included), and the evidence
pack — verified offline and pinned by md5. eval_report.json must be
byte-identical across runs.

Usage: python evals/run_evals.py [--report evals/eval_report.json]
Exit 0 iff every golden eval passes.
"""

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_gateway import scopes as scope_logic  # noqa: E402
from mcp_gateway.checks import run_checks  # noqa: E402
from mcp_gateway.demo import load_all  # noqa: E402
from mcp_gateway.diff import diff_person  # noqa: E402
from mcp_gateway.evidence import build_pack, verify_pack  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ctx():
    return load_all()


def scenario_catalog_shape():
    catalog, policy, grants, _ = _ctx()
    return {
        "servers": len(catalog.servers),
        "tools": len(catalog.all_tools()),
        "universe_scopes": len(catalog.universe_scopes()),
        "roles": len(policy.role_names()),
        "grants_examined": sum(len(v) for v in grants.values()),
        "catalog_problems": catalog.validate(),
        "policy_problems": policy.validate(catalog),
    }


def scenario_implication_graph():
    pairs = [
        ("crm:*", "crm:export"), ("crm:*", "billing:invoices:read"),
        ("crm", "crm:contacts:read"), ("crm:contacts", "crm:contacts:write"),
        ("billing:payments:write", "billing:payments:read"),
        ("billing:payments:read", "billing:payments:write"),
        ("billing:invoices:approve", "billing:invoices:read"),
        ("billing:invoices:approve", "billing:invoices:write"),
        ("docs:write", "docs:approve"),
        ("warehouse:write", "warehouse:export"),
        ("crm:contacts:admin", "crm:contacts:read"),
        ("code:repos:write", "code:pr:approve"),
    ]
    return {"implies": [scope_logic.implies(a, b) for a, b in pairs]}


def scenario_grant_findings():
    catalog, policy, grants, _ = _ctx()
    bundle = run_checks(catalog, policy, grants)
    return {
        "ids": [f["id"] for f in bundle["grant_findings"]],
        "by_type": bundle["summary"]["grant_findings_by_type"],
        "sales_wildcard_excess": next(
            f["excess"] for f in bundle["grant_findings"]
            if f["id"] == "WILDCARD_GRANT:sales_rep:crm:*"),
    }


def scenario_sod_findings():
    catalog, policy, grants, _ = _ctx()
    bundle = run_checks(catalog, policy, grants)
    return {"ids": [f["id"] for f in bundle["sod_findings"]]}


def scenario_coverage_gaps():
    catalog, policy, grants, _ = _ctx()
    bundle = run_checks(catalog, policy, grants)
    return {"roles_with_gaps": bundle["summary"]["roles_with_gaps"],
            "gaps": bundle["coverage_gaps"]}


def _diff_scenario(name):
    def fn():
        catalog, policy, grants, people = _ctx()
        person = next(p for p in people if p["name"] == name)
        d = diff_person(catalog, policy, grants, person)
        return {k: d[k] for k in ("kind", "gained_tools", "lost_tools",
                                  "gained_scopes", "lost_scopes",
                                  "creep_tools", "creep_scopes")}
    return fn


def scenario_evidence_pack():
    catalog, policy, grants, people = _ctx()
    pack = build_pack(catalog, policy, grants, people)
    ok, _ = verify_pack(pack, catalog, policy, grants, people)
    canon = json.dumps(pack, sort_keys=True, separators=(",", ":"))
    return {
        "verify_ok": ok,
        "audit_records": len(pack["audit_records"]),
        "total_findings": pack["summary"]["total_findings"],
        "pack_md5": hashlib.md5(canon.encode()).hexdigest(),
    }


SCENARIOS = {
    "catalog_shape": scenario_catalog_shape,
    "implication_graph": scenario_implication_graph,
    "grant_findings": scenario_grant_findings,
    "sod_findings": scenario_sod_findings,
    "coverage_gaps": scenario_coverage_gaps,
    "diff_priya_mover": _diff_scenario("priya"),
    "diff_marcus_mover": _diff_scenario("marcus"),
    "diff_jules_mover": _diff_scenario("jules"),
    "diff_ana_joiner": _diff_scenario("ana"),
    "diff_tom_leaver": _diff_scenario("tom"),
    "evidence_pack": scenario_evidence_pack,
}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default=os.path.join(ROOT, "evals", "eval_report.json"))
    ap.add_argument("--golden", default=os.path.join(ROOT, "evals", "golden.json"))
    a = ap.parse_args(argv)

    with open(a.golden, encoding="utf-8") as f:
        golden = json.load(f)

    results = []
    for name, fn in SCENARIOS.items():
        try:
            actual = fn()
            expected = golden[name]
            passed = actual == expected
            detail = "" if passed else f"expected {expected}, got {actual}"
        except Exception as e:  # noqa: BLE001
            actual, passed, detail = {"error": str(e)}, False, f"raised {e!r}"
        results.append({"name": name, "passed": passed,
                        "expected": golden.get(name), "actual": actual,
                        "detail": detail})
        print(f"{'PASS' if passed else 'FAIL'}  {name}" + (f"  {detail}" if detail else ""))

    report = {"evals": results,
              "passed": sum(r["passed"] for r in results),
              "total": len(results)}
    with open(a.report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")
    with open(a.report, "rb") as f:
        md5 = hashlib.md5(f.read()).hexdigest()
    print(f"\n{report['passed']}/{report['total']} golden evals passed; report md5={md5}")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
