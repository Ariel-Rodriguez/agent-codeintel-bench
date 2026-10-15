#!/usr/bin/env python3
"""Explicit, curated baseline snapshots; never discover or copy a user's files."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import re

# Deliberately narrow: unknown configuration is blocked, not silently ignored.
SETTINGS = {
    "compaction": {"enabled": bool, "reserveTokens": int, "keepRecentTokens": int},
    "retry": {"enabled": bool, "maxRetries": int, "baseDelayMs": int},
    "thinkingBudgets": {"minimal": int, "low": int, "medium": int, "high": int},
}
RESERVED_ENV = {"HOME", "PATH", "MODEL_GATEWAY", "LD_PRELOAD", "PYTHONPATH", "NODE_OPTIONS",
                "CODEINTEL_EXT", "TOOL_ENTRY", "GUIDANCE_FILE", "BASELINE_TOOLS", "ENHANCED_TOOLS"}
SECRET = re.compile(r"auth|token|secret|password|credential|api.?key|private.?key", re.I)


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def exact_keys(data, keys, label):
    if not isinstance(data, dict) or set(data) != set(keys):
        raise ValueError(f"{label}: expected only {', '.join(sorted(keys))}")


def validate_env(env):
    if not isinstance(env, dict) or any(not re.fullmatch(r"[A-Z_][A-Z0-9_]*", k) or
            k.startswith("PI_") or k in RESERVED_ENV or SECRET.search(k) or
            not isinstance(v, str) or "${" in v for k, v in env.items()):
        raise ValueError("snapshot/candidate environment must contain literal non-secret, non-reserved settings")


def validate_settings(settings):
    if not isinstance(settings, dict) or set(settings) - SETTINGS.keys():
        raise ValueError("unsupported snapshot settings; document limitation and block instead of dropping configuration")
    for group, values in settings.items():
        if not isinstance(values, dict) or set(values) - SETTINGS[group].keys():
            raise ValueError(f"unsupported {group} settings")
        for key, value in values.items():
            if type(value) is not SETTINGS[group][key] or (type(value) is int and value < 0):
                raise ValueError(f"invalid setting {group}.{key}")


def validate_assets(assets, *, extension=False):
    if not isinstance(assets, list):
        raise ValueError("assets must be an ordered list")
    for asset in assets:
        exact_keys(asset, {"entry", "revision", "sha256"} if extension else {"entry", "sha256"}, "asset")
        if not re.fullmatch(r"/opt/[^\s]+", asset["entry"]) or ".." in pathlib.PurePosixPath(asset["entry"]).parts:
            raise ValueError("snapshot assets must be explicitly provisioned below /opt, never host personal paths")
        if not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"]):
            raise ValueError("asset requires an exact sha256")
        if extension and not re.fullmatch(r"[0-9a-f]{40}|[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.-]+)?", asset["revision"]):
            raise ValueError("extension revision must be a full commit or exact version")
    if len({a["entry"] for a in assets}) != len(assets):
        raise ValueError("duplicate asset entries")


def validate_proofs(proofs, extensions):
    if not isinstance(proofs, list) or len(proofs) != len(extensions):
        raise ValueError("each pinned extension needs one activation proof contract")
    for proof, extension in zip(proofs, extensions):
        keys = {"id", "revision", "registered_tools", "executed_tools", "hooks", "settings", "source_evidence"}
        exact_keys(proof, keys | ({"wrapper_capture"} if "wrapper_capture" in proof else set()), "activation")
        if "wrapper_capture" in proof:
            exact_keys(proof["wrapper_capture"], {"instrumentation", "wrapper_implementations"}, "wrapper capture")
            if proof["hooks"] or set(proof["registered_tools"]) != set(proof["executed_tools"]):
                raise ValueError("wrapper capture proves executed wrappers only; use explicit probes for other registration/hooks")
        if proof["revision"] != extension["revision"] or not proof["id"] or not proof["source_evidence"]:
            raise ValueError("activation needs source-reviewed evidence and the pinned extension revision")
        if not proof["executed_tools"] and not proof["hooks"]:
            raise ValueError("registration alone is not treatment execution")
        if any(not isinstance(proof[k], list) or any(not isinstance(v, str) or not v for v in proof[k])
               for k in ("registered_tools", "executed_tools", "hooks")) or not isinstance(proof["settings"], dict):
            raise ValueError("invalid activation tools/hooks/settings")
        if not set(proof["executed_tools"]) <= set(proof["registered_tools"]):
            raise ValueError("executed tools must have declared registration evidence")
    if len({p["id"] for p in proofs}) != len(proofs):
        raise ValueError("duplicate activation implementation IDs")
    registered = [tool for p in proofs for tool in p["registered_tools"]]
    if len(registered) != len(set(registered)):
        raise ValueError("overlapping tool wrappers require a source-verified composition contract; currently unsupported")


def validate_snapshot(frozen):
    exact_keys(frozen, {"sha256", "data"}, "frozen snapshot")
    data = frozen["data"]
    exact_keys(data, {"kind", "pi_version", "model", "model_config_sha256", "tools", "extensions", "guidance_files", "settings", "env", "activation", "provenance"}, "snapshot")
    if frozen["sha256"] != digest(data):
        raise ValueError("personal/baseline snapshot sha256 mismatch")
    if data["kind"] not in ("vanilla", "personal") or not re.fullmatch(r"\d+\.\d+\.\d+", data["pi_version"]):
        raise ValueError("snapshot needs kind and exact Pi version")
    if data["model_config_sha256"] is not None and not re.fullmatch(r"[0-9a-f]{64}", data["model_config_sha256"]):
        raise ValueError("model configuration needs an exact hash or null for absent models.json")
    exact_keys(data["model"], {"provider", "model", "thinking"}, "model")
    if any(not isinstance(v, str) or not v or "${" in v for v in data["model"].values()):
        raise ValueError("model settings must be explicit literals")
    if not isinstance(data["tools"], list) or not data["tools"] or any(not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_*]*", t) for t in data["tools"]):
        raise ValueError("tools must be an explicit allowlist")
    validate_assets(data["extensions"], extension=True)
    validate_assets(data["guidance_files"])
    validate_env(data["env"])
    validate_settings(data["settings"])
    validate_proofs(data["activation"], data["extensions"])
    exact_keys(data["provenance"], {"actual_personal", "reviewed", "limitations"}, "provenance")
    if type(data["provenance"]["actual_personal"]) is not bool or type(data["provenance"]["reviewed"]) is not bool or not isinstance(data["provenance"]["limitations"], list):
        raise ValueError("invalid snapshot provenance")
    if data["kind"] == "vanilla" and (data["extensions"] or data["guidance_files"] or data["env"] or data["settings"]):
        raise ValueError("vanilla must have no personal extensions, guidance, settings or environment")
    return data


def snapshot_condition(condition):
    data = validate_snapshot(condition["snapshot"])
    result = dict(condition, **copy.deepcopy({k: data[k] for k in ("pi_version", "model", "model_config_sha256", "tools", "extensions", "guidance_files", "settings", "env", "activation")}),
                  extension=None, guidance_file=None, config_file=None, expected_activation={"extension_loaded": bool(data["extensions"])})
    provenance = data["provenance"]
    if not provenance["reviewed"] or provenance["limitations"] or (data["kind"] == "personal" and not provenance["actual_personal"]):
        result["blocked_reason"] = "Baseline not safely reproduced/reviewed as actual personal setup; limitations: " + json.dumps(provenance["limitations"])
    return result


def verify_runtime(condition, runtime):
    """Check observed launch metadata against the immutable resolved declaration."""
    reasons = []
    for field in ("pi_version", "model", "model_config_sha256", "settings", "extensions", "guidance_files"):
        if runtime.get(field) != condition.get(field):
            reasons.append(f"runtime {field} differs from frozen declaration")
    if runtime.get("effective_condition_env") != {k: condition["env"].get(k) for k in condition["env_keys"]}:
        reasons.append("runtime effective environment differs")
    from conditions import pi_flags
    expected = ["pi", "--provider", condition["model"]["provider"], "--model", condition["model"]["model"],
                "--thinking", condition["model"]["thinking"], *pi_flags(condition)]
    if runtime.get("command_flags") != expected:
        reasons.append("runtime launch flags differ")
    return reasons


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=pathlib.Path, help="manually curated snapshot JSON, NOT a Pi agent directory")
    parser.add_argument("output", type=pathlib.Path, help="new immutable snapshot descriptor")
    args = parser.parse_args()
    data = json.loads(args.source.read_text())
    frozen = {"sha256": digest(data), "data": data}
    validate_snapshot(frozen)
    # Refuse replacement; changes need a new snapshot identity and review.
    with args.output.open("x") as handle:
        handle.write(json.dumps(frozen, indent=2) + "\n")
    print(frozen["sha256"])


if __name__ == "__main__":
    main()
