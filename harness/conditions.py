#!/usr/bin/env python3
"""Host-side condition declarations. Labels never imply supported Kernel flags."""
from __future__ import annotations

import copy
import json
import os
import pathlib
import re

ORDERS = (("baseline", "kernel_full", "kernel_no_compression"),
          ("kernel_full", "kernel_no_compression", "baseline"),
          ("kernel_no_compression", "baseline", "kernel_full"),
          ("baseline", "kernel_no_compression", "kernel_full"),
          ("kernel_no_compression", "kernel_full", "baseline"),
          ("kernel_full", "baseline", "kernel_no_compression"))
CONTROL_ENV = {"CODEINTEL_EXT", "TOOL_ENTRY", "GUIDANCE_FILE", "BASELINE_TOOLS", "ENHANCED_TOOLS"}


def condition_orders(ids):
    """Preserve historical ABC order; use a balanced Latin square otherwise."""
    if set(ids) == set(ORDERS[0]):
        return ORDERS
    n = len(ids)
    if n < 2:
        raise ValueError("at least two conditions are required")
    first = [0]
    for i in range(1, n):
        first.append((i + 1) // 2 if i % 2 else n - i // 2)
    rows = [tuple(ids[(v + shift) % n] for v in first) for shift in range(n)]
    return tuple(rows + [tuple(reversed(row)) for row in rows]) if n % 2 else tuple(rows)


def expand_comparisons(data):
    """Opt-in dual-baseline schema. Inheritance, not copied settings, defines controls."""
    from baseline import (exact_keys, snapshot_condition, validate_assets, validate_env,
                          validate_proofs)
    candidate = data.get("candidate")
    exact_keys(candidate, {"extension", "tools", "env", "guidance_files", "activation"}, "candidate")
    validate_assets([candidate["extension"]], extension=True)
    validate_assets(candidate["guidance_files"])
    validate_env(candidate["env"])
    validate_proofs([candidate["activation"]], [candidate["extension"]])
    if not isinstance(candidate["tools"], list) or any(not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_*]*", t) for t in candidate["tools"]):
        raise ValueError("candidate tools must be an explicit allowlist")
    originals = {c["id"]: c for c in data["conditions"]}
    expanded = {}
    for cid, c in originals.items():
        if "inherits" not in c:
            exact_keys(c, {"id", "image", "snapshot"}, "comparison baseline")
            expanded[cid] = snapshot_condition(c)
    for cid, c in originals.items():
        if "inherits" not in c:
            continue
        exact_keys(c, {"id", "inherits"}, "candidate condition")
        if c["inherits"] not in expanded or "inherits" in expanded[c["inherits"]]:
            raise ValueError("candidate must inherit directly from a frozen baseline")
        parent = expanded[c["inherits"]]
        if any(k in parent["env"] and parent["env"][k] != v for k, v in candidate["env"].items()):
            raise ValueError("candidate may not override baseline environment")
        result = copy.deepcopy(parent)
        result.update(id=cid, inherits=c["inherits"])
        result["extensions"] += [candidate["extension"]]
        result["guidance_files"] += candidate["guidance_files"]
        result["tools"] += [t for t in candidate["tools"] if t not in result["tools"]]
        result["env"].update(candidate["env"])
        result["activation"] += [candidate["activation"]]
        result["expected_activation"] = {"extension_loaded": True}
        validate_assets(result["extensions"], extension=True)
        validate_assets(result["guidance_files"])
        validate_proofs(result["activation"], result["extensions"])
        expanded[cid] = result
    comparisons = data["comparisons"]
    ids = [p["id"] for p in comparisons]
    if not ids or len(ids) != len(set(ids)) or any(not re.fullmatch(r"[a-z][a-z0-9_]*", i) for i in ids):
        raise ValueError("comparison IDs must be unique safe identifiers")
    for pair in comparisons:
        if set(pair) - {"id", "purpose", "baseline", "candidate"}:
            raise ValueError("unknown comparison fields")
        purpose = pair.get("purpose", pair["id"])
        left, right = expanded.get(pair["baseline"]), expanded.get(pair["candidate"])
        if purpose not in ("scientific", "adoption") or not left or not right or right.get("inherits") != left["id"]:
            raise ValueError("comparison needs scientific/adoption purpose and baseline plus inherited candidate")
        if left["snapshot"]["data"]["kind"] != ("personal" if purpose == "adoption" else "vanilla"):
            raise ValueError("comparison purpose does not match baseline kind")
        if left["model"] != right["model"] or left["image"] != right["image"]:
            raise ValueError("paired model and image must be identical")
    if {c for p in comparisons for c in (p["baseline"], p["candidate"])} != set(expanded):
        raise ValueError("every comparison condition must belong to a declared pair")
    if not data.get("baseline_differences"):
        raise ValueError("document vanilla/personal baseline differences")
    data["conditions"] = [expanded[c["id"]] for c in data["conditions"]]


def load_manifest(path):
    data = json.loads(pathlib.Path(path).read_text())
    conditions = data["conditions"]
    ids = [c["id"] for c in conditions]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r"[a-z][a-z0-9_]*", cid) for cid in ids):
        raise ValueError("condition IDs must be unique safe identifiers")
    if "comparisons" in data:
        expand_comparisons(data)
        conditions = data["conditions"]
    limits = data.get("limits", {})
    if any(type(limits.get(k)) is not int or limits[k] <= 0 for k in ("wall_seconds", "output_bytes")):
        raise ValueError("positive equal wall_seconds and output_bytes limits are required")
    for c in conditions:
        for key in ("image", "extension", "tools", "guidance_file", "env", "config_file", "expected_activation"):
            if key not in c:
                raise ValueError(f"{c['id']}: missing {key}")
        if not isinstance(c["env"], dict) or any(not re.fullmatch(r"[A-Z_][A-Z0-9_]*", k) or
                                                k.startswith("PI_") or k in CONTROL_ENV | {"HOME", "PATH", "MODEL_GATEWAY", "LD_PRELOAD", "PYTHONPATH", "NODE_OPTIONS"}
                                                for k in c["env"]):
            raise ValueError(f"{c['id']}: unsafe or harness-reserved environment key")
    by_id = {c["id"]: c for c in conditions}
    if "comparisons" not in data and "kernel_no_compression" in by_id:
        b, c = by_id.get("kernel_full"), by_id["kernel_no_compression"]
        if not b:
            raise ValueError("C requires B")
        for key in ("image", "extension", "extension_revision", "tools", "guidance_file", "profile"):
            if b.get(key) != c.get(key):
                raise ValueError(f"B/C must have identical {key}")
        control = data.get("compression_control") or {}
        if not control.get("verified"):
            c["blocked_reason"] = c.get("blocked_reason") or "No source-verified independent compression switch for the pinned Kernel revision"
        else:
            if not control.get("source_evidence") or control.get("revision") != b.get("extension_revision"):
                raise ValueError("compression control needs source evidence for the exact extension revision")
            differences = {k for k in b["env"].keys() | c["env"].keys() if b["env"].get(k) != c["env"].get(k)}
            if not differences <= set(control.get("env_keys", [])):
                raise ValueError("B/C environment differs outside verified compression controls")
            if b.get("config_file") != c.get("config_file") and not control.get("config_files_verified"):
                raise ValueError("B/C config differences need source verification")
    return data


def resolve_condition(manifest, condition_id, *, environ=None):
    environ = os.environ if environ is None else environ
    original = next(c for c in manifest["conditions"] if c["id"] == condition_id)
    unresolved = []

    def expand(value):
        if isinstance(value, str):
            def replace(match):
                key = match[1]
                if not environ.get(key):
                    unresolved.append(key)
                return environ.get(key, "")
            return re.sub(r"\$\{([A-Z_][A-Z0-9_]*)\}", replace, value)
        if isinstance(value, list):
            return [expand(v) for v in value]
        if isinstance(value, dict):
            return {k: expand(v) for k, v in value.items()}
        return value
    resolved = expand(original)
    resolved["limits"] = manifest["limits"].copy()
    resolved["env_keys"] = sorted({k for c in manifest["conditions"] for k in c["env"]})
    if unresolved:
        resolved["blocked_reason"] = resolved.get("blocked_reason") or "Unresolved required variables: " + ", ".join(sorted(set(unresolved)))
    return resolved


def execution_env(condition, inherited=None):
    inherited = os.environ if inherited is None else inherited
    # Keep runtime infrastructure only. In particular no ambient Kernel/profile
    # variables (including ones unknown to this harness) reach another cell.
    allowed = {"PATH", "HOME", "USER", "LANG", "TMPDIR", "TMP", "TEMP", "NODE_PATH",
               "HF_HOME", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "XDG_CACHE_HOME",
               "PI_PROVIDER", "PI_MODEL", "PI_THINKING", "PI_CODING_AGENT_DIR",
               "PI_CODING_AGENT_SESSION_DIR", "PI_USER_AGENT_DIR", "MODEL_GATEWAY"}
    env = {k: v for k, v in inherited.items() if k in allowed or k.startswith("LC_")}
    env.update(PI_SKIP_VERSION_CHECK="1", PI_TELEMETRY="0")
    env.update({k: str(v) for k, v in condition["env"].items()})
    return env


def pi_flags(condition):
    flags = ["--mode", "json", "--print", "--no-extensions", "--no-mcp", "--no-skills",
             "--no-prompt-templates", "--no-themes", "--no-context-files", "--no-approve",
             "--tools", ",".join(condition["tools"])]
    entries = [a["entry"] for a in condition.get("extensions", [])]
    if condition.get("extension"):
        entries.append(condition["extension"])
    for entry in entries:
        flags += ["-e", entry]
    guidance = [a["entry"] for a in condition.get("guidance_files", [])]
    if condition.get("guidance_file"):
        guidance.append(condition["guidance_file"])
    for entry in guidance:
        flags += ["--append-system-prompt", entry]
    return flags
