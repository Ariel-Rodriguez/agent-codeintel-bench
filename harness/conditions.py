#!/usr/bin/env python3
"""Host-side condition declarations. Labels never imply supported Kernel flags."""
from __future__ import annotations

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


def load_manifest(path):
    data = json.loads(pathlib.Path(path).read_text())
    conditions = data["conditions"]
    ids = [c["id"] for c in conditions]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r"[a-z][a-z0-9_]*", cid) for cid in ids):
        raise ValueError("condition IDs must be unique safe identifiers")
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
    if "kernel_no_compression" in by_id:
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
    if condition.get("extension"):
        flags += ["-e", condition["extension"]]
    if condition.get("guidance_file"):
        flags += ["--append-system-prompt", condition["guidance_file"]]
    return flags
