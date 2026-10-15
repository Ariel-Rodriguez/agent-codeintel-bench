"""Synthetic declarations and captures only: NOT personal configuration or measurements."""
import copy
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from baseline import digest
from conditions import pi_flags

ROOT = pathlib.Path(__file__).resolve().parents[2]


def manifest():
    data = json.loads((ROOT / "experiments/dual-baseline.json").read_text())
    # Synthetic unit-test attestation; this file never describes the owner's setup.
    personal = data["conditions"][2]["snapshot"]["data"]
    personal["provenance"] = {"actual_personal": True, "reviewed": True, "limitations": []}
    extension = {"entry": "/opt/personal/helper.ts", "revision": "1" * 40, "sha256": "1" * 64}
    personal["extensions"] = [extension]
    proof = copy.deepcopy(data["candidate"]["activation"])
    proof.update(id="personal.helper", revision=extension["revision"], registered_tools=[], executed_tools=[], hooks=["before_agent_start"])
    personal["activation"] = [proof]
    data["conditions"][2]["snapshot"]["sha256"] = digest(personal)
    # IDs deliberately do not encode roles.
    names = {"vanilla": "plain", "vanilla_candidate": "plus", "personal": "configured", "personal_candidate": "configured_plus"}
    for condition in data["conditions"]:
        condition["id"] = names[condition["id"]]
        if "inherits" in condition:
            condition["inherits"] = names[condition["inherits"]]
    for pair in data["comparisons"]:
        for key in ("baseline", "candidate"):
            pair[key] = names[pair[key]]
    return data


def capture(cell, condition, *, tokens=100, text="correct"):
    """Write synthetic output shaped like the runner's captured evidence."""
    events, audit = [], []
    for proof in condition["activation"]:
        common = {k: proof[k] for k in ("id", "revision", "settings")}
        common["conflicts"] = []
        audit.append(dict(common, phase="loaded", registered_tools=proof["registered_tools"]))
        for hook in proof["hooks"]:
            audit.append(dict(common, phase="hook", hook=hook, success=True))
        for tool in proof["executed_tools"]:
            cid = f"{proof['id']}/{tool}"
            events += [{"type": "tool_execution_start", "toolCallId": cid, "toolName": tool, "args": {}},
                       {"type": "tool_execution_end", "toolCallId": cid, "isError": False,
                        "result": {"content": [{"type": "text", "text": "synthetic output"}]}}]
            audit.append(dict(common, phase="execute", tool=tool, toolCallId=cid, success=True))
    events.append({"type": "message_end", "message": {"role": "assistant", "stopReason": "stop",
                   "content": [{"type": "text", "text": text}],
                   "usage": {"input": tokens - 10, "output": 10, "totalTokens": tokens}}})
    (cell / "stdout.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    (cell / "activation.jsonl").write_text("".join(json.dumps(e) + "\n" for e in audit))
    (cell / "exit_code").write_text("0\n")
    (cell / "wall_seconds").write_text("1\n")
    (cell / "termination.json").write_text(json.dumps({"reason": "completed", "exit_code": 0}))
    runtime = {k: condition[k] for k in ("pi_version", "model", "model_config_sha256", "settings", "extensions", "guidance_files", "prompt_sha256")}
    runtime.update(condition=condition,
                   effective_condition_env={k: condition["env"].get(k) for k in condition["env_keys"]},
                   command_flags=["pi", "--provider", condition["model"]["provider"], "--model", condition["model"]["model"],
                                  "--thinking", condition["model"]["thinking"], *pi_flags(condition)])
    (cell / "runtime_metadata.json").write_text(json.dumps(runtime))
