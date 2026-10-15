#!/usr/bin/env python3
"""Minimal allowlist gateway: the only egress path for the bench container.

The bench container sits on an internal Docker network with no route to the
internet. The gateway is attached to that network *and* to the normal bridge, and
forwards requests to exactly one upstream (the model API). A benchmark container
can therefore reach the model and nothing else, so an untrusted extension cannot
exfiltrate to arbitrary hosts.

Env:
    UPSTREAM_BASE_URL   e.g. https://model.example/v1
    GATEWAY_PORT        default 8080
"""
from __future__ import annotations

import http.server
import os
import urllib.error
import urllib.request

UPSTREAM = os.environ.get("UPSTREAM_BASE_URL", "").rstrip("/")
PORT = int(os.environ.get("GATEWAY_PORT", "8080"))

if not UPSTREAM:
    raise SystemExit("gateway: UPSTREAM_BASE_URL is required (the model /v1 base URL)")

# Headers that must not be copied verbatim.
HOP_BY_HOP = {"host", "content-length", "connection", "transfer-encoding", "keep-alive"}


class Gateway(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:  # quieter logs
        print(f"gateway {self.address_string()} {fmt % args}", flush=True)

    def _forward(self, method: str) -> None:
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length) if length else None
        url = UPSTREAM + self.path
        request = urllib.request.Request(url, data=body, method=method)
        for key, value in self.headers.items():
            if key.lower() not in HOP_BY_HOP:
                request.add_header(key, value)
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                payload = response.read()
                self.send_response(response.status)
                for key, value in response.headers.items():
                    if key.lower() not in HOP_BY_HOP:
                        self.send_header(key, value)
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            self.send_response(exc.code)
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as exc:  # noqa: BLE001 - report and deny
            message = f"gateway error: {exc}".encode()
            self.send_response(502)
            self.send_header("content-length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)

    def do_GET(self) -> None:  # noqa: N802
        self._forward("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._forward("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._forward("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._forward("DELETE")


if __name__ == "__main__":
    print(f"gateway: 0.0.0.0:{PORT} -> {UPSTREAM}", flush=True)
    http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Gateway).serve_forever()
