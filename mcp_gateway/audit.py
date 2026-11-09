"""Hash-chained JSONL audit log.

Format reused from the sibling build tool-approval-gate (see README
footnote): every record is one JSON line carrying the sha256 of the
previous record's hash, so deleting or editing a line breaks the chain —
`verify()` recomputes it. This is tamper-EVIDENCE, not tamper-PROOF (a
writer holding the file can always rewrite history); the README of the
originating build says so honestly, and so does this one.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Callable


def _canonical(record: dict) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


def _hash(prev_hash: str, record: dict) -> str:
    return hashlib.sha256((prev_hash + _canonical(record)).encode()).hexdigest()


def verify_records(records: list[dict]) -> tuple[bool, str]:
    """Recompute the chain over an in-memory record list (evidence packs
    embed their audit records, so verification must not need the file)."""
    prev = "0" * 64
    expected_seq = 0
    for rec in records:
        expected_seq += 1
        if rec.get("seq") != expected_seq:
            return False, f"seq break at record {rec.get('seq')}"
        body = {k: v for k, v in rec.items() if k != "hash"}
        if _hash(prev, body) != rec.get("hash"):
            return False, f"hash mismatch at seq {expected_seq}"
        prev = rec["hash"]
    return True, f"chain valid: {expected_seq} records"


class AuditLog:
    def __init__(self, path: str, clock: Callable[[], float] | None = None):
        self.path = path
        self._clock = clock or time.time
        self._seq = 0
        self._prev_hash = "0" * 64
        if os.path.exists(path):
            self._replay()

    def _replay(self) -> None:
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                self._seq = max(self._seq, rec["seq"])
                self._prev_hash = rec["hash"]

    def append(self, event: str, **fields) -> dict:
        self._seq += 1
        record = {"seq": self._seq, "ts": self._clock(), "event": event}
        record.update(fields)
        record["hash"] = _hash(self._prev_hash, record)
        self._prev_hash = record["hash"]
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(_canonical(record) + "\n")
        return record

    def read_all(self) -> list[dict]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def verify(self) -> tuple[bool, str]:
        return verify_records(self.read_all())
