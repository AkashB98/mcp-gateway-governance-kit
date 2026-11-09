# mcp-gateway-governance-kit

**Access creep is what happens between role changes.** Someone moves from
sales to support, the ticket says "remove the old role, add the new one,"
and the paper diff looks clean — two tools lost, two gained. But their
*actual grants* tell a different story: a wildcard picked up in the old
role still makes three tools usable, including a bulk-export tool they
were **never assigned**. This kit computes that gap instead of asserting
it: a local MCP server/tool catalog, one policy model, a scope-implication
graph that decides what a grant really confers, and a joiner/mover/leaver
simulator whose headline number is the creep.

## The headline case (seeded, computed — not scripted)

Priya moves `sales_rep` → `support_rep`:

| | tools | scopes |
|---|---|---|
| Paper diff (policy) | −2 lost, +2 gained | −2 / +2 |
| **Creep if old grants are kept** | **3 still usable** | **3 retained** |

The creep includes `crm.export_contacts` — never in her old role's policy
at all. It is reachable only because her grants contain `crm:*`, and the
implication graph expands that wildcard to `crm:export`. No individual
check finds this; it falls out of grants × implication × the role change.

## Why this exists (the hiring signal)

MCP gateways are becoming enterprise infrastructure, and enterprises
govern infrastructure: who may call which server, with which OAuth
scopes, and what happens to that access when people join, move, and
leave. (JD-backed: a Senior Staff AI Enablement Engineer posting at SoFi,
2026-11-09, asks for exactly this — MCP governance, least-privilege
access, audit evidence.) The sibling builds gate individual tool calls
(`tool-approval-gate`) and lint tool schemas (`tool-schema-linter`); this
one governs the *standing access* behind the calls — the layer an auditor
reviews, not the layer a single request hits.

## Quickstart

```bash
python3 mcp_gateway/cli.py demo        # end-to-end scenario, asserts inline
python3 mcp_gateway/cli.py check       # seeded fixtures: 8 findings, exit 1
python3 mcp_gateway/cli.py catalog     # servers / tools / scopes
python3 mcp_gateway/cli.py policy      # the one policy table
python3 mcp_gateway/cli.py diff --person priya
python3 mcp_gateway/cli.py evidence --out var/evidence   # pack + summary
python3 mcp_gateway/cli.py verify --pack var/evidence/evidence_pack.json
python3 mcp_gateway/cli.py serve --port 8473             # JSON API on 127.0.0.1
```

## The model

**Catalog** (`fixtures/catalog.json`) — 5 fictional MCP servers (crm,
billing, code-host, docs, warehouse), 18 tools. Each tool declares the
OAuth scopes it requires, an action (`read/create/approve/write/export`),
and a resource class (`invoices`, `pull_requests`, …). The 18 distinct
required scopes form the *universe* grants expand into.

**One policy model** (`fixtures/policy.json`) — a single table:
`role → allowed servers → allowed tools`. There is no separate scope
table to drift out of sync: a role's allowed scopes are **derived** from
its tools via the catalog. Grants (`fixtures/grants.json`) are what the
identity provider *actually* issued per role. Governance is the
comparison: should-have (policy) vs do-have (grants).

## Scope implication — the real logic

A grant confers more than its literal string. `scopes.py` models it:

- **wildcard** — `crm:*` implies every scope under `crm:`
- **parent** — `crm` implies `crm:contacts:read`; `crm:contacts` implies its children
- **verb ladder** (same resource) — `…:admin` → `…:write`/`…:approve`/`…:read`; `…:write` → `…:read`; `…:approve` → `…:read`
- `…:write` does **not** imply `…:approve` (writing is not approving), and
  nothing in the ladder implies `…:export` — bulk export is never a
  side effect of ordinary write access. Both negatives are pinned by tests.

Over-broad detection is defined entirely by expansion against the universe:

- **WILDCARD_GRANT** — any wildcard grant, flagged on sight: even when its
  excess is empty *today* (`warehouse:*` for data_engineer), every future
  scope under the prefix arrives silently. Excess lists today's over-cover.
- **UNUSED_GRANT** — the grant's expansion overlaps nothing the role's
  tools require (e.g. a stray `warehouse:read` held by finance_lead).
- **IMPLIED_EXCESS** — the grant covers a real need but drags unneeded
  power with it: `billing:payments:write` held where only the implied
  read is ever used.

Seeded results: **6 findings over 26 grants** (3 wildcard, 2 unused,
1 implied-excess) — all 6 planted cases detected, 0 false positives on
the 20 clean grants (precision 1.0 / recall 1.0 *on the seeded fixtures*;
that is a fixture score, not a claim about real IdP data).

**Segregation of duties** is a policy-level check, independent of grants:
a role that can both **create** and **approve** the same resource class
can push its own work through. Seeded: **2 conflicts** —
`finance_lead` (create + approve invoices) and `eng_lead` (create +
approve pull requests); both planted, both detected.

**Coverage gaps** run the other direction: required scopes no grant
confers. Seeded fixtures have none (every role can actually do its job);
a test pins the detector by revoking grants synthetically.

## Joiner / mover / leaver

`diff` computes, for a role change, the exact policy diff (gained/lost
tools + scopes) **and** the creep: the old role's real grants, expanded
through the implication graph, minus what the new role needs — plus every
tool those retained grants still make usable.

- **Movers**: priya (above) and marcus — his clerk grants keep
  `billing.refund_payment` usable in his new analyst role, another tool
  he was never assigned. Jules' promotion is the control case: creep
  shrinks to 1 scope, because his previously-unused secrets grant becomes
  legitimate in the new role.
- **Joiner** (ana): creep = day-one over-provisioning inside the new
  role's own grants. Seeded: 0.
- **Leaver** (tom): creep = the full revocation list — 7 tools / 7 scopes
  still usable if finance_lead's grants aren't revoked, including
  `warehouse.query_data` reached via the stray grant, outside his role
  entirely.

## Audit evidence

`evidence` emits one JSON **evidence pack** (catalog shape, all findings,
all five diffs, summary counts) with the run's steps recorded in a
hash-chained audit log embedded in the pack, plus a short Markdown
summary **rendered from the pack** — the .md is a view, never a second
source of truth. `verify` works offline: it recomputes every finding and
diff from the fixture inputs, compares field-by-field, and re-verifies
the hash chain. Editing a finding, a count, or an audit record fails
verification (all three tampers are pinned by tests).

## API

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | `{ok: true}` |
| GET | `/catalog` | servers, tools, scope universe |
| GET | `/policy` | role → servers → tools, with derived scopes |
| GET | `/check` | full governance findings bundle |
| POST | `/diff` | `{person}` or `{from_role, to_role}` → access diff + creep |

## Architecture

```
mcp_gateway/
  scopes.py      the implication graph: implies() / expand() / covers()
  catalog.py     Server / Tool registry, scope universe, validation
  policy.py      THE policy model: role -> servers -> tools (scopes derived)
  checks.py      over-broad grants (via implication), SoD, coverage gaps
  diff.py        joiner/mover/leaver diffs; creep from ACTUAL grants
  audit.py       hash-chained JSONL audit log (see footnote)
  evidence.py    evidence pack build / offline verify / markdown render
  server.py      stdlib http.server JSON API (127.0.0.1 only; demo surface)
  cli.py         catalog | policy | check | grants | diff | evidence |
                 verify | demo | serve
  demo.py        scripted Helios Home scenario, asserts inline, serve trip
fixtures/        catalog.json · policy.json · grants.json · people.json
```

## Tests & evals

```bash
python3 -m unittest discover -s tests          # 45 hermetic tests, stdlib only
python3 evals/run_evals.py                     # 11 golden evals
```

The golden evals pin exact behavior — finding ids and excess lists, SoD
ids, all five diffs' gained/lost/creep lists, and the evidence pack's
md5. `eval_report.json` is committed and byte-identical across runs
(md5 `4de6bebc363fb42bbb53cb5df3eb6143`).

## Dev-loop honesty

No logic bug survived to a green test run in this build; what the
verification loop did catch was in the *expectations*, which is its own
lesson for an evals-driven project:

1. **A hand-counted golden was wrong, the engine was right.** The
   leaver case was first hand-pinned at 4 lost tools; the computed diff
   said 5 — `finance_lead` also holds `docs.read_doc`. The golden file
   was corrected only after manually re-deriving the set from the policy
   table. Golden files are claims, and claims get audited too.
2. **A design decision the fixtures forced:** an excess-only definition
   of "over-broad" would pass `warehouse:*` for data_engineer (its
   expansion exactly matches today's needs). The fixture exists
   precisely to pin the stricter rule — wildcards are flagged on sight,
   because their real excess is the *future* scopes under the prefix.

## Honest limits

- **Fixtures only.** No real MCP connections, no live IdP, no SCIM —
  catalog, policy, grants, and people are fictional JSON (Helios Home).
  A production port would sync the catalog from gateway registrations
  and grants from the IdP, and re-run the same checks on a schedule.
- The implication graph reasons over scope *strings* by the documented
  rules; real providers differ in wildcard and hierarchy semantics, so
  the rules would be calibrated per provider before trusting verdicts.
- SoD is checked at role granularity (create+approve in one role);
  person-level SoD across multiple simultaneously-held roles is out of
  scope for this build.
- Single-node, no auth on the API — an ops/demo surface on localhost.

All fixtures are fictional. Stdlib only. No network in tests (the core
is exercised with sockets stubbed out; the demo's localhost round-trip
is the only socket use, and it is opt-in there).

---

*Footnote: the hash-chained JSONL audit format in `audit.py` is reused
from the sibling build `tool-approval-gate`, where it records gate
decisions; here it records governance runs inside the evidence pack.
It is a supporting mechanism, not this build's subject.*
