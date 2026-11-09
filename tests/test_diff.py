"""Unit tests: joiner/mover/leaver diffs and access-creep computation."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_gateway.demo import load_all
from mcp_gateway.diff import diff_person, usable_tools


class TestDiff(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog, cls.policy, cls.grants, cls.people = load_all()
        cls.by_name = {p["name"]: p for p in cls.people}

    def _diff(self, name):
        return diff_person(self.catalog, self.policy, self.grants,
                           self.by_name[name])

    def test_priya_mover_creep_exceeds_paper_diff(self):
        d = self._diff("priya")
        self.assertEqual(d["kind"], "mover")
        self.assertEqual(d["gained_tools"],
                         ["billing.view_invoice", "billing.view_payment"])
        self.assertEqual(d["lost_tools"],
                         ["crm.create_contact", "docs.create_doc"])
        self.assertEqual(d["gained_scopes"],
                         ["billing:invoices:read", "billing:payments:read"])
        self.assertEqual(d["lost_scopes"], ["crm:contacts:write", "docs:write"])
        # Creep is computed from her ACTUAL grants: the crm:* wildcard keeps
        # crm.export_contacts usable — a tool she was never even assigned.
        self.assertEqual(d["creep_tools"],
                         ["crm.create_contact", "crm.export_contacts",
                          "docs.create_doc"])
        self.assertEqual(d["creep_scopes"],
                         ["crm:contacts:write", "crm:export", "docs:write"])
        self.assertGreater(len(d["creep_tools"]), len(d["lost_tools"]))

    def test_marcus_mover_keeps_unassigned_refund_tool(self):
        d = self._diff("marcus")
        self.assertEqual(d["creep_tools"],
                         ["billing.create_invoice", "billing.refund_payment",
                          "billing.view_invoice", "billing.view_payment"])
        self.assertEqual(d["creep_scopes"],
                         ["billing:invoices:read", "billing:invoices:write",
                          "billing:payments:read", "billing:payments:write"])

    def test_jules_promotion_creep_shrinks_to_one(self):
        d = self._diff("jules")
        self.assertEqual(d["gained_tools"],
                         ["code-host.approve_pr", "code-host.manage_secrets"])
        self.assertEqual(d["lost_tools"], ["docs.create_doc"])
        # His previously-unused secrets grant becomes legitimate in the new
        # role, so only the docs write access creeps.
        self.assertEqual(d["creep_tools"], ["docs.create_doc"])
        self.assertEqual(d["creep_scopes"], ["docs:write"])

    def test_ana_joiner_no_creep(self):
        d = self._diff("ana")
        self.assertEqual(d["kind"], "joiner")
        self.assertEqual(d["gained_tools"],
                         ["crm.search_contacts", "docs.read_doc",
                          "warehouse.query_data"])
        self.assertEqual(d["lost_tools"], [])
        self.assertEqual(d["creep_tools"], [])
        self.assertEqual(d["creep_scopes"], [])

    def test_tom_leaver_residual_is_full_revocation_list(self):
        d = self._diff("tom")
        self.assertEqual(d["kind"], "leaver")
        self.assertEqual(len(d["lost_tools"]), 5)
        self.assertEqual(len(d["lost_scopes"]), 5)
        self.assertEqual(d["creep_tools"],
                         ["billing.approve_invoice", "billing.create_invoice",
                          "billing.refund_payment", "billing.view_invoice",
                          "billing.view_payment", "docs.read_doc",
                          "warehouse.query_data"])
        self.assertEqual(len(d["creep_scopes"]), 7)
        # The stray warehouse:read grant reaches a tool outside his old role.
        self.assertIn("warehouse.query_data", d["creep_tools"])

    def test_usable_tools_respects_implication(self):
        usable = usable_tools(self.catalog, ["crm:*"])
        self.assertIn("crm.export_contacts", usable)
        self.assertNotIn("billing.view_invoice", usable)


if __name__ == "__main__":
    unittest.main()
