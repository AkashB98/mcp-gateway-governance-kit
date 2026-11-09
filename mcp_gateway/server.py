"""Tiny stdlib JSON API for the governance kit.

    GET  /health   -> {ok: true}
    GET  /catalog  -> servers, tools, scope universe
    GET  /policy   -> role -> servers -> tools, with derived scopes
    GET  /check    -> governance findings bundle
    POST /diff     -> {person} or {from_role, to_role} -> access diff

State is the loaded fixtures in memory; this is a demo/ops surface on
localhost, not a production gateway — the README says so.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from .checks import run_checks
from .diff import diff_access, diff_person


def make_server(catalog, policy, grants, people, port: int = 8473) -> HTTPServer:
    people_by_name = {p["name"]: p for p in people}

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code: int, obj) -> None:
            body = json.dumps(obj, sort_keys=True).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if not length:
                return {}
            return json.loads(self.rfile.read(length).decode())

        def do_GET(self):
            try:
                if self.path == "/health":
                    return self._send(200, {"ok": True})
                if self.path == "/catalog":
                    return self._send(200, {
                        "servers": [{
                            "id": s.id, "name": s.name,
                            "tools": [{"id": t.id, "scopes": list(t.scopes),
                                       "action": t.action,
                                       "resource": t.resource}
                                      for t in s.tools],
                        } for s in catalog.servers],
                        "universe_scopes": catalog.universe_scopes(),
                    })
                if self.path == "/policy":
                    return self._send(200, {
                        role: {
                            "servers": policy.roles[role],
                            "tools": policy.allowed_tool_ids(role),
                            "scopes": policy.required_scopes(catalog, role),
                        } for role in policy.role_names()})
                if self.path == "/check":
                    return self._send(200, run_checks(catalog, policy, grants))
                return self._send(404, {"error": "not found"})
            except Exception as e:  # noqa: BLE001 - demo surface
                return self._send(500, {"error": str(e)})

        def do_POST(self):
            try:
                body = self._read_json()
                if self.path == "/diff":
                    if "person" in body:
                        person = people_by_name[body["person"]]
                        return self._send(200, diff_person(
                            catalog, policy, grants, person))
                    return self._send(200, diff_access(
                        catalog, policy, grants,
                        body.get("from_role"), body.get("to_role")))
                return self._send(404, {"error": "not found"})
            except KeyError as e:
                return self._send(404, {"error": str(e)})
            except Exception as e:  # noqa: BLE001 - demo surface
                return self._send(500, {"error": str(e)})

    return HTTPServer(("127.0.0.1", port), _Handler)


def serve(catalog, policy, grants, people, port: int = 8473) -> None:
    httpd = make_server(catalog, policy, grants, people, port)
    print(f"mcp-gateway-governance-kit serving on http://127.0.0.1:{port}")
    httpd.serve_forever()
