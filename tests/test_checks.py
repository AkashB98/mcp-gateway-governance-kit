"""Unit tests: over-broad grant findings, SoD conflicts, coverage gaps."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_gateway.checks import coverage_gaps, grant_findings, run_checks, sod_findings
from mcp_gateway.demo import load_all

EXPECTED_GRANT_IDS = [
    "IMPLIED_EXCESS:billing_clerk:billing:payments:write",
    "UNUSED_GRANT:eng_staff:code:secrets:write",
    "UNUSED_GRANT:finance_lead:warehouse:read",
    "WILDCARD_GRANT:data_engineer:warehouse:*",
    "WILDCARD_GRANT:finance_lead:billing:*",
    "WILDCARD_GRANT:sales_rep:crm:*",
]

EXPECTED_SOD_IDS = [
    "SOD:eng_lead:pull_requests:code-host.create_pr+code-host.approve_pr",
    "SOD:finance_lead:invoices:billing.create_invoice+billing.approve_invoice",
]


class TestChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog, cls.policy, cls.grants, cls.people = load_all()

    def test_grant_findings_exact(self):
        findings = grant_findings(self.catalog, self.policy, self.grants)
        self.assertEqual([f["id"] for f in findings], EXPECTED_GRANT_IDS)

    def test_grant_finding_excess_uses_implication(self):
        findings = {f["id"]: f for f in
                    grant_findings(self.catalog, self.policy, self.grants)}
        # The wildcard's excess is a scope no sales tool requires, reached
        # only through the implication graph.
        self.assertEqual(
            findings["WILDCARD_GRANT:sales_rep:crm:*"]["excess"], ["crm:export"])
        # Write-where-read-suffices: the excess is the write scope itself.
        self.assertEqual(
            findings["IMPLIED_EXCESS:billing_clerk:billing:payments:write"]
            ["excess"], ["billing:payments:write"])
        # A wildcard can be a finding with NO current excess (future scopes).
        self.assertEqual(
            findings["WILDCARD_GRANT:data_engineer:warehouse:*"]["excess"], [])

    def test_clean_roles_have_no_findings(self):
        findings = grant_findings(self.catalog, self.policy, self.grants)
        flagged_roles = {f["role"] for f in findings}
        self.assertNotIn("support_rep", flagged_roles)
        self.assertNotIn("analyst", flagged_roles)
        self.assertNotIn("eng_lead", flagged_roles)

    def test_sod_findings_exact(self):
        findings = sod_findings(self.catalog, self.policy)
        self.assertEqual([f["id"] for f in findings], EXPECTED_SOD_IDS)

    def test_coverage_gaps_empty_on_fixtures(self):
        gaps = coverage_gaps(self.catalog, self.policy, self.grants)
        self.assertTrue(all(v == [] for v in gaps.values()), gaps)

    def test_coverage_gap_detected_when_grant_removed(self):
        grants = {r: list(v) for r, v in self.grants.items()}
        grants["analyst"] = ["docs:read"]  # warehouse + crm grants revoked
        gaps = coverage_gaps(self.catalog, self.policy, grants)
        self.assertEqual(gaps["analyst"],
                         ["crm:contacts:read", "warehouse:read"])

    def test_run_checks_summary(self):
        bundle = run_checks(self.catalog, self.policy, self.grants)
        self.assertEqual(bundle["summary"], {
            "grant_findings": 6,
            "grant_findings_by_type": {
                "WILDCARD_GRANT": 3, "UNUSED_GRANT": 2, "IMPLIED_EXCESS": 1},
            "sod_findings": 2,
            "roles_with_gaps": 0,
            "total_findings": 8,
        })
        self.assertEqual(bundle["grants_examined"], 26)


if __name__ == "__main__":
    unittest.main()
