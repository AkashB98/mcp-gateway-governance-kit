"""mcp-gateway-governance-kit: govern MCP servers like infrastructure.

A local registry of MCP servers and tools, one policy model
(role -> servers -> tools, scopes derived), a scope-implication graph
that decides what a grant actually confers, over-broad and
segregation-of-duties checks, a joiner/mover/leaver simulator whose
headline is access creep on role changes, and an offline-verifiable
audit evidence pack.
"""

from .catalog import Catalog, Server, Tool, load_catalog, load_catalog_file
from .policy import Policy, load_policy, load_policy_file, load_grants, load_people
from . import scopes
from .checks import grant_findings, sod_findings, coverage_gaps, run_checks
from .diff import diff_access, diff_person, usable_tools
from .audit import AuditLog, verify_records
from .evidence import build_pack, verify_pack, render_markdown

__all__ = [
    "Catalog", "Server", "Tool", "load_catalog", "load_catalog_file",
    "Policy", "load_policy", "load_policy_file", "load_grants", "load_people",
    "scopes", "grant_findings", "sod_findings", "coverage_gaps", "run_checks",
    "diff_access", "diff_person", "usable_tools",
    "AuditLog", "verify_records",
    "build_pack", "verify_pack", "render_markdown",
]
