#!/usr/bin/env python3
"""Heuristic static scan of a code-intelligence extension for risky capabilities.

This is a triage aid, not proof of safety or malice. Absence of matches is not
evidence that an extension is harmless.

Usage:
    harness/scan_extension.py <extension-path> [--json]
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

RULES = [
    ("critical", "process execution", r"child_process|execSync|spawnSync|\bexec\(|\bspawn\(|\bfork\("),
    ("critical", "filesystem writes", r"fs\.(write|append|unlink|rm|rmdir|chmod|rename|truncate)|createWriteStream"),
    ("high", "network access", r"net\.(connect|createConnection)|dgram\.|http\.request|https\.request|\bfetch\(|WebSocket|XMLHttpRequest"),
    ("high", "environment / user introspection", r"process\.env|os\.homedir|os\.userInfo"),
    ("high", "credential / secret paths", r"/etc/passwd|/etc/shadow|id_rsa|\.ssh/|\.aws/|\.pi/agent|credentials|auth\.json"),
    ("high", "dynamic code execution", r"\beval\(|new Function\(|vm\.(run|compile)"),
    ("medium", "filesystem reads", r"fs\.(readFile|readFileSync|createReadStream|readdir)"),
    ("medium", "risky module import", r"require\(['\"](child_process|net|dgram|http|https|tls)['\"]\)|from ['\"](child_process|net|dgram|http|https|tls)['\"]"),
    ("medium", "possible obfuscation", r"base64|Buffer\.from\([^,]+,\s*['\"]base64"),
]

SOURCE_SUFFIXES = (".ts", ".js", ".mjs", ".cjs")


def iter_sources(target: pathlib.Path):
    for path in sorted(target.rglob("*")):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        if "node_modules" in path.parts or ".git" in path.parts:
            continue
        yield path


def scan(target: pathlib.Path) -> dict:
    findings = []
    files = list(iter_sources(target))
    for path in files:
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for lineno, text in enumerate(lines, start=1):
            for severity, rule, pattern in RULES:
                if re.search(pattern, text):
                    findings.append(
                        {
                            "severity": severity,
                            "rule": rule,
                            "file": str(path),
                            "line": lineno,
                            "text": text.strip()[:160],
                        }
                    )
    return {"extension": str(target), "files": len(files), "findings": findings}


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    target = pathlib.Path(argv[0])
    if not target.exists():
        print(f"not found: {target}", file=sys.stderr)
        return 2
    result = scan(target)

    if "--json" in argv[1:]:
        print(json.dumps(result))
        return 0

    print(f"Scanning: {target} ({result['files']} source files)\n")
    for severity in ("critical", "high", "medium"):
        rows = [f for f in result["findings"] if f["severity"] == severity]
        if not rows:
            continue
        print(f"[{severity}]")
        for row in rows:
            print(f"    {row['file']}:{row['line']}: {row['text']}")
    total = len(result["findings"])
    print(f"\nTotal matches: {total}")
    if total:
        print("Verdict: REVIEW — run untrusted code only under `docker/run.sh probe` (no network).")
    else:
        print("Verdict: no heuristic hits (still untrusted: absence of matches is not safety).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
