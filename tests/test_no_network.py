"""No-network guard: catalog, checks, diffs and evidence must all work
with sockets ripped out. (The demo's live localhost round-trip is opt-in
and lives in demo.py, not in the hermetic core.)"""

import os
import socket
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _NoSockets:
    def __init__(self, *a, **k):
        raise AssertionError("network access forbidden in hermetic tests")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestNoNetwork(unittest.TestCase):
    def test_core_flows_without_sockets(self):
        real_socket = socket.socket
        socket.socket = _NoSockets
        try:
            from mcp_gateway import demo
            demo.run(serve_roundtrip=False)  # full core scenario, no network
        finally:
            socket.socket = real_socket


if __name__ == "__main__":
    unittest.main()
