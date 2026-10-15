#!/usr/bin/env python3
"""Allowlisted gateway: the only egress path for the bench container.

The bench container sits on an internal Docker network with no route to the
internet. The gateway is attached to that network *and* to the normal bridge, and
forwards requests to exactly one upstream origin. A benchmark container can
therefore reach the model and nothing else, so an untrusted extension cannot
exfiltrate to arbitrary hosts.

UPSTREAM_BASE_URL is the model **origin** (no path, no /v1). Request paths are
forwarded verbatim, so a request to /v1/chat/completions becomes
<origin>/v1/chat/completions.

Env:
    UPSTREAM_BASE_URL   e.g. http://local-model:8000   (origin only)
    GATEWAY_PORT        default 8080
"""
from __future__ import annotations

import http.server
import os
import urllib.error
import urllib.request

UPSTREAM = os.environ.get("UPSTREAM_BASE_URL", "").rstrip("/")
PORT = int(os.environ.get("GATEWAY_PORT", "8080"))

ALLOWED_METHODS = {"GET", "POST"}
ALLOWED_PREFIXES = ("/v1/",)

HOP_BY_HOP = {"host", "content-length", "connection", "transfer-encoding", "keep-alive"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


# Never consult environment proxies, and never follow redirects.
OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    _NoRedirect(),
)

if not UPSTREAM:
    raise SystemExit("gateway: UPSTREAM_BASE_URL is required (the model origin, no /v1)")


class Gateway(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"gateway {self.address_string()} {fmt % args}", flush=True)

    def _deny(self, code: int, message: str) -> None:
        body = message.encode()
        self.send_response(code)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _forward(self, method: str) -> None:
        if method not in ALLOWED_METHODS:
            self._deny(405, "gateway: method not allowed")
            return
        if not any(self.path.startswith(prefix) for prefix in ALLOWED_PREFIXES):
            self._deny(403, "gateway: path not allowed")
            return

        length = int(self.headers.get("content-length") or 0)
        if length > 64 * 1024 * 1024:
            self._deny(413, "gateway: request too large")
            return
        body = self.rfile.read(length) if length else None

        request = urllib.request.Request(UPSTREAM + self.path, data=body, method=method)
        for key, value in self.headers.items():
            if key.lower() not in HOP_BY_HOP:
                request.add_header(key, value)

        try:
            with OPENER.open(request, timeout=900) as response:
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
            self._deny(502, f"gateway error: {exc}")

    def do_GET(self) -> None:  # noqa: N802
        self._forward("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._forward("POST")


if __name__ == "__main__":
    print(f"gateway: 0.0.0.0:{PORT} -> {UPSTREAM} (origin; /v1/ paths only)", flush=True)
    http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Gateway).serve_forever()
