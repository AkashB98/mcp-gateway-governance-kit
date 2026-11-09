"""Unit tests: the scope-implication graph (implies / expand / covers)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_gateway import scopes


class TestImplies(unittest.TestCase):
    def test_exact(self):
        self.assertTrue(scopes.implies("crm:contacts:read", "crm:contacts:read"))

    def test_global_wildcard(self):
        self.assertTrue(scopes.implies("*", "billing:invoices:approve"))

    def test_prefix_wildcard(self):
        self.assertTrue(scopes.implies("crm:*", "crm:export"))
        self.assertTrue(scopes.implies("crm:*", "crm:contacts:write"))
        self.assertFalse(scopes.implies("crm:*", "billing:invoices:read"))

    def test_parent_implies_child(self):
        self.assertTrue(scopes.implies("crm", "crm:contacts:read"))
        self.assertTrue(scopes.implies("crm:contacts", "crm:contacts:read"))
        self.assertFalse(scopes.implies("crm:contacts", "crm:export"))

    def test_write_implies_read(self):
        self.assertTrue(scopes.implies("billing:payments:write",
                                       "billing:payments:read"))
        self.assertTrue(scopes.implies("docs:write", "docs:read"))
        self.assertFalse(scopes.implies("docs:read", "docs:write"))

    def test_approve_implies_read_not_write(self):
        self.assertTrue(scopes.implies("billing:invoices:approve",
                                       "billing:invoices:read"))
        self.assertFalse(scopes.implies("billing:invoices:approve",
                                        "billing:invoices:write"))

    def test_admin_ladder(self):
        self.assertTrue(scopes.implies("crm:contacts:admin", "crm:contacts:write"))
        self.assertTrue(scopes.implies("crm:contacts:admin", "crm:contacts:read"))
        self.assertFalse(scopes.implies("crm:contacts:write", "crm:contacts:admin"))

    def test_write_does_not_imply_approve_or_export(self):
        self.assertFalse(scopes.implies("docs:write", "docs:approve"))
        self.assertFalse(scopes.implies("warehouse:write", "warehouse:export"))
        self.assertFalse(scopes.implies("crm:contacts:write", "crm:export"))

    def test_cross_resource_never_implies(self):
        self.assertFalse(scopes.implies("code:repos:write", "code:pr:approve"))
        self.assertFalse(scopes.implies("billing:invoices:write",
                                        "billing:payments:read"))


class TestExpandCovers(unittest.TestCase):
    UNIVERSE = ["crm:contacts:read", "crm:contacts:write", "crm:export",
                "docs:read", "docs:write"]

    def test_expand_wildcard(self):
        self.assertEqual(scopes.expand(["crm:*"], self.UNIVERSE),
                         ["crm:contacts:read", "crm:contacts:write", "crm:export"])

    def test_expand_write_pulls_read(self):
        self.assertEqual(scopes.expand(["docs:write"], self.UNIVERSE),
                         ["docs:read", "docs:write"])

    def test_expand_empty(self):
        self.assertEqual(scopes.expand([], self.UNIVERSE), [])

    def test_covers(self):
        self.assertTrue(scopes.covers(["docs:write"], "docs:read"))
        self.assertFalse(scopes.covers(["docs:read"], "docs:write"))


if __name__ == "__main__":
    unittest.main()
