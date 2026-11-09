"""Unit tests: evidence pack build, offline verify, tamper evidence."""

import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_gateway.demo import load_all
from mcp_gateway.evidence import build_pack, render_markdown, verify_pack


class TestEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog, cls.policy, cls.grants, cls.people = load_all()
        cls.pack = build_pack(cls.catalog, cls.policy, cls.grants, cls.people)

    def _verify(self, pack):
        return verify_pack(pack, self.catalog, self.policy, self.grants,
                           self.people)

    def test_pack_summary(self):
        self.assertEqual(self.pack["summary"]["total_findings"], 8)
        self.assertEqual(self.pack["grants_examined"], 26)
        self.assertEqual(len(self.pack["diffs"]), 5)
        self.assertTrue(self.pack["audit_chain"]["valid"])

    def test_verify_clean_pack(self):
        ok, msg = self._verify(self.pack)
        self.assertTrue(ok, msg)

    def test_verify_detects_edited_finding(self):
        pack = copy.deepcopy(self.pack)
        pack["grant_findings"] = pack["grant_findings"][:-1]  # drop a finding
        ok, msg = self._verify(pack)
        self.assertFalse(ok)
        self.assertIn("do not match", msg)

    def test_verify_detects_edited_count(self):
        pack = copy.deepcopy(self.pack)
        pack["summary"]["grant_findings"] = 0
        ok, _ = self._verify(pack)
        self.assertFalse(ok)

    def test_verify_detects_tampered_audit_record(self):
        pack = copy.deepcopy(self.pack)
        pack["audit_records"][1]["grant_findings"] = 0
        ok, msg = self._verify(pack)
        self.assertFalse(ok)
        self.assertIn("hash mismatch", msg)

    def test_markdown_rendered_from_pack(self):
        md = render_markdown(self.pack)
        self.assertIn("Grant findings: 6", md)
        self.assertIn("Segregation-of-duties conflicts: 2", md)
        self.assertIn("priya", md)
        self.assertIn("crm.export_contacts", md)
        for f in self.pack["grant_findings"]:
            self.assertIn(f["id"], md)


if __name__ == "__main__":
    unittest.main()
