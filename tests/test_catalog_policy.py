"""Unit tests: catalog shape, the single policy model, derived scopes."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_gateway.demo import load_all


class TestCatalogPolicy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog, cls.policy, cls.grants, cls.people = load_all()

    def test_catalog_shape(self):
        self.assertEqual(self.catalog.server_ids(),
                         ["billing", "code-host", "crm", "docs", "warehouse"])
        self.assertEqual(len(self.catalog.all_tools()), 18)
        self.assertEqual(len(self.catalog.universe_scopes()), 18)

    def test_validation_clean(self):
        self.assertEqual(self.catalog.validate(), [])
        self.assertEqual(self.policy.validate(self.catalog), [])

    def test_required_scopes_derive_from_tools(self):
        self.assertEqual(
            self.policy.required_scopes(self.catalog, "sales_rep"),
            ["crm:contacts:read", "crm:contacts:write", "docs:read", "docs:write"])
        self.assertEqual(
            self.policy.required_scopes(self.catalog, "analyst"),
            ["crm:contacts:read", "docs:read", "warehouse:read"])

    def test_allowed_tools_single_table(self):
        self.assertEqual(
            self.policy.allowed_tool_ids("finance_lead"),
            ["billing.approve_invoice", "billing.create_invoice",
             "billing.view_invoice", "billing.view_payment", "docs.read_doc"])

    def test_unknown_role_raises(self):
        with self.assertRaises(KeyError):
            self.policy.allowed_tool_ids("nobody")

    def test_grants_cover_every_role(self):
        self.assertEqual(sorted(self.grants), self.policy.role_names())
        total = sum(len(v) for v in self.grants.values())
        self.assertEqual(total, 26)


if __name__ == "__main__":
    unittest.main()
