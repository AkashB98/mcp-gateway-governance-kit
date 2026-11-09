"""End-to-end demo: governing a fictional MCP gateway (Helios Home).

Deterministic throughout (fixture data + a fixed-step clock inside the
evidence pack). Exercises: catalog load, the scope-implication graph,
over-broad + segregation-of-duties checks, the mover case where access
creep exceeds the paper diff, the leaver residual, evidence pack build +
offline verify, and a live localhost serve round-trip.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.request

from . import scopes as scope_logic
from .catalog import load_catalog
from .checks import run_checks
from .diff import diff_person
from .evidence import build_pack, render_markdown, verify_pack
from .policy import load_grants, load_people, load_policy
from .server import make_server

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "fixtures")


def load_all():
    with open(os.path.join(FIXTURES, "catalog.json"), encoding="utf-8") as f:
        catalog = load_catalog(json.load(f))
    with open(os.path.join(FIXTURES, "policy.json"), encoding="utf-8") as f:
        policy = load_policy(json.load(f))
    with open(os.path.join(FIXTURES, "grants.json"), encoding="utf-8") as f:
        grants = load_grants(json.load(f))
    with open(os.path.join(FIXTURES, "people.json"), encoding="utf-8") as f:
        people = load_people(json.load(f))
    return catalog, policy, grants, people


def run(serve_roundtrip: bool = True) -> None:
    catalog, policy, grants, people = load_all()
    print("== mcp-gateway-governance-kit demo: Helios Home (fictional) ==")

    # 1. Catalog + policy validate clean.
    assert catalog.validate() == [] and policy.validate(catalog) == []
    print(f"1. catalog             -> {len(catalog.servers)} servers, "
          f"{len(catalog.all_tools())} tools, "
          f"{len(catalog.universe_scopes())} scopes in universe")

    # 2. The implication graph: what a grant ACTUALLY confers.
    assert scope_logic.implies("crm:*", "crm:export")
    assert scope_logic.implies("billing:payments:write", "billing:payments:read")
    assert scope_logic.implies("crm", "crm:contacts:read")
    assert not scope_logic.implies("docs:write", "docs:approve")
    assert not scope_logic.implies("warehouse:write", "warehouse:export")
    print("2. implication graph   -> wildcard / parent / write->read hold; "
          "write does NOT imply approve or export")

    # 3. Governance checks over the seeded grants + policy.
    checks = run_checks(catalog, policy, grants)
    s = checks["summary"]
    assert s["grant_findings"] == 6, s
    assert s["grant_findings_by_type"] == {
        "WILDCARD_GRANT": 3, "UNUSED_GRANT": 2, "IMPLIED_EXCESS": 1}, s
    assert s["sod_findings"] == 2, s
    assert s["roles_with_gaps"] == 0, s
    print(f"3. governance check    -> {s['grant_findings']} over-broad grants "
          f"(3 wildcard, 2 unused, 1 implied-excess), {s['sod_findings']} "
          f"segregation-of-duties conflicts, 0 coverage gaps")

    # 4. The headline: Priya moves sales_rep -> support_rep. The paper diff
    #    says she loses 2 tools; her retained grants actually keep 3 tools
    #    usable — including crm.export_contacts, which she was NEVER assigned.
    priya = next(p for p in people if p["name"] == "priya")
    d = diff_person(catalog, policy, grants, priya)
    assert d["lost_tools"] == ["crm.create_contact", "docs.create_doc"], d
    assert d["creep_tools"] == ["crm.create_contact", "crm.export_contacts",
                                "docs.create_doc"], d
    assert d["creep_scopes"] == ["crm:contacts:write", "crm:export",
                                 "docs:write"], d
    print("4. mover creep (priya) -> paper diff loses 2 tools, but retained "
          "grants keep 3 usable — incl. crm.export_contacts, never assigned "
          "(the crm:* wildcard she picked up in sales)")

    # 5. Leaver residual: Tom's stray grants reach beyond his old role.
    tom = next(p for p in people if p["name"] == "tom")
    d = diff_person(catalog, policy, grants, tom)
    assert len(d["creep_tools"]) == 7 and len(d["creep_scopes"]) == 7, d
    assert "warehouse.query_data" in d["creep_tools"], d
    print("5. leaver residual     -> tom (finance_lead) leaves with 7 tools / "
          "7 scopes still usable if grants aren't revoked — incl. "
          "warehouse.query_data via a stray warehouse:read grant")

    # 6. Evidence pack: build, verify offline, render the summary from it.
    pack = build_pack(catalog, policy, grants, people)
    ok, msg = verify_pack(pack, catalog, policy, grants, people)
    assert ok, msg
    md = render_markdown(pack)
    assert "priya" in md and "crm.export_contacts" in md, md
    print(f"6. evidence pack       -> built + verified offline "
          f"({pack['audit_chain']['message']}); markdown summary rendered "
          f"from the pack")

    # 7. Live localhost round-trip (skipped by the no-network test).
    if serve_roundtrip:
        httpd = make_server(catalog, policy, grants, people, port=0)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/health", timeout=5) as r:
                assert json.loads(r.read()) == {"ok": True}
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/check", timeout=5) as r:
                body = json.loads(r.read())
            assert body["summary"]["total_findings"] == 8, body["summary"]
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/diff",
                data=json.dumps({"person": "priya"}).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                body = json.loads(r.read())
            assert "crm.export_contacts" in body["creep_tools"], body
        finally:
            httpd.shutdown()
            httpd.server_close()
        print("7. serve round-trip    -> /health, /check (8 findings), "
              "POST /diff (priya creep) all answered on 127.0.0.1")

    print("\ndemo complete: creep is computed, not asserted — every number "
          "above came out of the implication graph over the fixtures.")


if __name__ == "__main__":
    run()
