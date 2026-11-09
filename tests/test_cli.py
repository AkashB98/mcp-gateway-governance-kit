"""Unit tests: CLI commands over the shipped fixtures (in-process)."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_gateway import cli


def _run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli.main(argv)
    return code, buf.getvalue()


class TestCli(unittest.TestCase):
    def test_catalog(self):
        code, out = _run(["catalog"])
        self.assertEqual(code, 0)
        self.assertIn("universe: 18 scopes, 18 tools, 5 servers", out)

    def test_policy_single_role(self):
        code, out = _run(["policy", "--role", "analyst"])
        self.assertEqual(code, 0)
        self.assertIn("warehouse:read", out)

    def test_check_reports_findings_and_exits_1(self):
        code, out = _run(["check"])
        self.assertEqual(code, 1)  # seeded fixtures carry findings by design
        self.assertIn("8 findings (6 grant, 2 SoD)", out)
        self.assertIn("WILDCARD_GRANT:sales_rep:crm:*", out)

    def test_diff_person_json(self):
        code, out = _run(["diff", "--person", "priya"])
        self.assertEqual(code, 0)
        d = json.loads(out)
        self.assertIn("crm.export_contacts", d["creep_tools"])

    def test_diff_unknown_person_exits_2(self):
        code, _ = _run(["diff", "--person", "nobody"])
        self.assertEqual(code, 2)

    def test_evidence_then_verify_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            code, _ = _run(["evidence", "--out", td])
            self.assertEqual(code, 0)
            pack_path = os.path.join(td, "evidence_pack.json")
            self.assertTrue(os.path.exists(pack_path))
            self.assertTrue(os.path.exists(
                os.path.join(td, "evidence_summary.md")))
            code, out = _run(["verify", "--pack", pack_path])
            self.assertEqual(code, 0)
            self.assertIn("pack verified", out)


if __name__ == "__main__":
    unittest.main()
