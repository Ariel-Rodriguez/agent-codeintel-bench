#!/usr/bin/env python3
"""Verify executed wrapper evidence, not extension registration or built-in names.

No source-independent probe can instrument Kernel's execute functions. Without
source-reviewed instrumentation and captured production probe evidence, BLOCKED
is the only valid outcome. This command performs no network or model calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib

from conditions import load_manifest, pi_flags, resolve_condition
from evaluate import load_events, normalize_tool_calls, verify_activation


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_capture(directory, condition, *, probe=False):
    calls = normalize_tool_calls(load_events(directory / "stdout.jsonl"))
    audit_path = directory / "wrapper_audit.jsonl"
    audit = load_events(audit_path) if audit_path.exists() else None
    result = verify_activation(calls, condition=condition, audit=audit)
    reasons = []
    if audit is None:
        reasons.append("missing execute-function wrapper_audit.jsonl; tool names/load registration cannot prove execution")
    instrumentation = condition.get("instrumentation") or {}
    if not instrumentation.get("patch_sha256") or not instrumentation.get("execute_locations") or instrumentation.get("revision") != condition.get("extension_revision"):
        reasons.append("missing source-reviewed instrumentation patch hash, revision and execute-function locations")
    expected = condition.get("expected_activation") or {}
    identities = expected.get("wrapper_implementations") or {}
    if not isinstance(expected.get("settings"), dict) or not all(k in expected["settings"] for k in ("compression", "retrieval")):
        reasons.append("missing source-verified expected effective compression/retrieval settings")
    if condition.get("blocked_reason"):
        reasons.append(condition["blocked_reason"])
    required = expected.get("wrapper_tools", [])
    if not required or any(not identities.get(t) for t in required):
        reasons.append("missing source-verified wrapper implementation IDs for required built-in-name tools")
    by_id = {c["toolCallId"]: c for c in calls}
    valid_audit = []
    errors = []
    for r in audit or []:
        if r.get("phase") != "complete":
            continue
        c = by_id.get(r.get("toolCallId"))
        if not c:
            errors.append({"toolCallId": r.get("toolCallId"), "reason": "audit call not present in trace"})
            continue
        error = None
        if r.get("success") is not (c["isError"] is False):
            error = "audit completion success disagrees with trace result"
        elif identities.get(c["name"]) != r.get("implementation_id"):
            error = "implementation ID not source-verified for this tool"
        elif not isinstance(r.get("settings"), dict) or not all(k in r["settings"] for k in ("compression", "retrieval")):
            error = "missing effective compression/retrieval settings"
        elif expected.get("settings") is not None and r["settings"] != expected["settings"]:
            error = "effective settings differ from declared expected settings"
        elif not all(isinstance(r.get(k), str) for k in ("pre_text", "post_text")):
            error = "missing captured pre/post text for host-side evidence verification"
        else:
            for prefix in ("pre", "post"):
                text = r[f"{prefix}_text"]
                if r.get(f"{prefix}_text_bytes") != len(text.encode("utf-8")) or r.get(f"{prefix}_sha256") != sha(text):
                    error = f"{prefix} bytes/hash do not match captured text"
            if r.get("compression_changed") is not (r["pre_text"] != r["post_text"]):
                error = "compression_changed disagrees with captured text"
            if c["text"] != r["post_text"]:
                error = "audited post text differs from model-visible text"
        if error:
            errors.append({"toolCallId": c["toolCallId"], "reason": error})
        else:
            valid_audit.extend(s for s in audit if s.get("toolCallId") == c["toolCallId"])
    verified = verify_activation(calls, condition=condition, audit=valid_audit if audit is not None else None)
    if verified["activation_status"] != "verified":
        reasons.append("required wrappers did not execute with joined, valid entry/completion evidence")
    if probe:
        # The host must capture these facts from the sandbox launcher/inspection,
        # not from model-visible content. Do not treat a load probe as execution.
        attestation_file = directory / "probe_host.json"
        attestation = json.loads(attestation_file.read_text()) if attestation_file.exists() else {}
        if attestation.get("network_mode") != "none" or not attestation.get("image_digest"):
            reasons.append("missing host no-network/image-digest probe attestation")
        if attestation.get("production_flags") != pi_flags(condition):
            reasons.append("probe flags differ from exact production --no-extensions/-e/--tools flags")
        if not verified.get("code_search_wrapper_executions"):
            reasons.append("offline probe did not execute code_search (registration is insufficient)")
        if any(c["name"] in required + ["code_search"] and c["isError"] is not False for c in calls):
            reasons.append("probe tool did not complete successfully")
    return {"status": "verified" if not reasons and not errors else "BLOCKED", "reasons": reasons,
            "audit_errors": errors, "execution": verified,
            "observed_tool_name_calls": result["code_search_calls"],
            "code_search_execution": verified["code_search_wrapper_executions"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conditions", required=True, type=pathlib.Path)
    parser.add_argument("--condition-id")
    parser.add_argument("--cell", type=pathlib.Path, help="real cell or host-captured offline compatibility probe")
    parser.add_argument("--probe", action="store_true", help="also require exact flags, no-network attestation and search execution")
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(argv)
    manifest = load_manifest(args.conditions)
    if args.cell and not args.condition_id:
        parser.error("--cell requires --condition-id")
    results = {}
    for c in manifest["conditions"]:
        if args.condition_id and c["id"] != args.condition_id:
            continue
        if c["expected_activation"].get("extension_loaded") is False:
            results[c["id"]] = {"status": "not_required"}
            continue
        resolved = resolve_condition(manifest, c["id"])
        if args.cell:
            results[c["id"]] = check_capture(args.cell, resolved, probe=args.probe)
        else:
            results[c["id"]] = {"status": "BLOCKED", "reasons": [resolved.get("blocked_reason") or
                "Supply a host-captured no-network production probe and real-cell execute audit; loading alone is not execution"]}
    if not results:
        parser.error("unknown condition ID")
    output = json.dumps(results, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(output)
    print(output, end="")
    return 2 if any(r["status"] == "BLOCKED" for r in results.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
