import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import evaluate as ev


def assistant(content=None, **extra):
    return {"type": "message_end", "message": {"role": "assistant", "content": content or [], **extra}}


def tool(cid, name="read", args=None, text="ok", details=None, error=False):
    return [{"type": "tool_execution_start", "toolCallId": cid, "toolName": name, "args": args or {}},
            {"type": "tool_execution_end", "toolCallId": cid, "isError": error, "durationMs": 2,
             "result": {"content": [{"type": "text", "text": text}], "details": details}}]


def calls(*groups):
    events = []
    for group in groups:
        events += [assistant()] + group
    return ev.normalize_tool_calls(events)


class EvaluationTests(unittest.TestCase):
    def test_join_fallback_visible_output_and_utf8(self):
        events = [assistant([{"type": "toolCall", "id": "x", "name": "read", "arguments": {"path": "fallback"}}])]
        events += tool("x", args={"path": "actual"}, text="not delivered")
        events += [{"type": "message_end", "message": {"role": "toolResult", "toolCallId": "x", "content": [
            {"type": "text", "text": "é"}, {"type": "image", "data": "ignored"}]}}]
        c = ev.normalize_tool_calls(events)
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]["args"]["path"], "actual")
        self.assertEqual(c[0]["text_source"], "toolResult")
        self.assertEqual(ev.response_metrics(c)["tool_response_text_bytes"], 2)
        self.assertIsNone(ev.response_metrics(c)["tool_response_tokens_est"])
        fallback = ev.normalize_tool_calls([events[0], events[2]])
        self.assertEqual(fallback[0]["args"]["path"], "fallback")

    def test_model_result_turn_wins_over_late_execution_end(self):
        events = [assistant(), tool("1")[0], {"type": "message_end", "message": {
            "role": "toolResult", "toolCallId": "1", "content": [{"type": "text", "text": "visible"}]}},
            assistant(), tool("1", text="fallback")[1]]
        c = ev.normalize_tool_calls(events)[0]
        self.assertEqual(c["turn"], 1)
        self.assertEqual(c["text"], "visible")

    def test_same_assistant_batch_is_not_post_truncation_recovery(self):
        events = [assistant()] + tool("1", args={"path": "a"}, details={"truncated": True}) + tool("2", args={"path": "a"})
        c = ev.normalize_tool_calls(events)
        self.assertEqual(ev.recovery_metrics(c, spec={}, audit=None)["post_truncation_retrieval_calls"], 0)

    def test_diagnostic_first_delivery_not_call_start_order(self):
        events = [assistant()] + tool("omitted", text="summary") + [assistant()]
        events += [tool("slow")[0], tool("fast")[0], tool("fast", text="DIAG")[1], assistant(), tool("slow", text="DIAG")[1]]
        c = ev.normalize_tool_calls(events)
        audit = [{"toolCallId": "omitted", "phase": "complete", "pre_text": "DIAG", "post_text": "summary"}]
        m = ev.recovery_metrics(c, spec={"diagnostics": [{"id": "d", "text": "DIAG"}]}, audit=audit)
        self.assertEqual(m["diagnostic_episodes"][0]["recovered_call_id"], "fast")
        self.assertEqual(m["diagnostic_recovery_turns"], [1])

    def test_ranges_union_default_and_success(self):
        c = calls(tool("1", args={"path": "./a", "limit": 10}),
                  tool("2", args={"path": "/workspace/a", "offset": 6, "limit": 10}),
                  tool("3", args={"path": "b/../a", "limit": 10}),
                  tool("4", args={"path": "a"}), tool("5", args={"path": "a"}),
                  tool("6", args={"path": "a"}, error=True))
        m = ev.retrieval_metrics(c, spec={})
        self.assertEqual(m["repeat_file_read_calls"], 4)
        self.assertEqual(m["repeat_read_range_calls"], 2)
        self.assertEqual(m["overlap_read_requested_lines"], 15)
        self.assertEqual(m["bounded_read_coverage"], 3 / 5)

    def test_mutation_splits_shell_exactness_and_tests(self):
        c = calls(tool("a", args={"path": "a"}), tool("b", args={"path": "a"}),
                  tool("edit", "edit"), tool("c", args={"path": "a"}),
                  tool("shell", "bash", {"command": "custom-script"}), tool("d", args={"path": "a"}),
                  tool("t1", "bash", {"command": " pytest -q "}),
                  tool("t2", "bash", {"command": "pytest -q"}),
                  tool("s1", "bash", {"command": 'rg "word" a.py'}),
                  tool("s2", "bash", {"command": "rg 'word' a.py"}))
        m = ev.retrieval_metrics(c, spec={})
        self.assertEqual(m["repetition_by_mutation"]["repeat_file_read_calls"], {
            "no_intervening_mutation": 1, "intervening_mutation": 1, "unknown": 1})
        self.assertEqual(m["repeat_bash_command_calls"], 1)
        self.assertEqual(m["repeat_bash_test_calls"], 1)
        self.assertEqual(m["repeat_bash_retrieval_calls"], 0)

    def test_overlap_concurrency_is_mutation_unknown(self):
        events = tool("1", args={"path": "a"})
        events.insert(1, tool("2", args={"path": "a"})[0])
        events.append(tool("2")[1])
        c = ev.normalize_tool_calls(events)
        m = ev.retrieval_metrics(c, spec={})
        self.assertEqual(m["repetition_by_mutation"]["repeat_file_read_calls"]["unknown"], 1)

    def test_truncation_unknown_false_and_versioned_marker(self):
        c = calls(tool("1", text="TRUNC"), tool("2", details={"truncation": {"truncated": True}}),
                  tool("3", details={"truncated": False}))
        m = ev.recovery_metrics(c, spec={}, audit=None)
        self.assertEqual(m["truncated_tool_responses"], 1)
        self.assertEqual(m["truncation_unknown_calls"], 1)
        self.assertIsNone(m["diagnostic_unrecovered_count"])
        spec = {"pi_version": "1.2.0", "truncation_markers": [{"pi_version": "other", "text": "TRUNC"}]}
        self.assertIsNone(ev.truncation_evidence(c[0], spec)[0])
        spec["truncation_markers"][0]["pi_version"] = "1.2.0"
        self.assertTrue(ev.truncation_evidence(c[0], spec)[0])

    def test_associations_window_distinct_and_bounded_overlap(self):
        c = calls(tool("1", args={"path": "a", "limit": 10}, details={"truncated": True}),
                  tool("2", args={"path": "a", "limit": 5}, details={"truncated": True}),
                  tool("3", args={"path": "a", "limit": 5}),
                  tool("4", "bash", {"command": "pytest -q"}),
                  tool("5", args={"path": "b"}), tool("6", args={"path": "b"}),
                  tool("7", args={"path": "a", "offset": 20, "limit": 5}))
        m = ev.recovery_metrics(c, spec={}, audit=None)
        self.assertEqual(m["post_truncation_retrieval_calls"], 3)  # 2,3,7 (within five turns of 2)
        self.assertEqual(m["post_truncation_repeat_read_calls"], 2)
        self.assertEqual(len(m["post_truncation_links"]), 4)

    def test_diagnostic_requires_pre_output_and_retains_censoring(self):
        c = calls(tool("1", text="summary"), tool("2", text="DIAG"), tool("3", text="summary"))
        spec = {"diagnostics": [{"id": "d", "text": "DIAG"}]}
        audit = [{"toolCallId": cid, "phase": "complete", "pre_text": "DIAG", "post_text": "summary"}
                 for cid in ("1", "3")]
        m = ev.recovery_metrics(c, spec=spec, audit=audit)
        self.assertEqual(m["diagnostic_recovery_turns"], [1])
        self.assertEqual(m["diagnostic_unrecovered_count"], 1)
        self.assertTrue(m["diagnostic_episodes"][1]["right_censored"])
        missing = ev.recovery_metrics(c, spec=spec, audit=[])
        self.assertEqual(missing["diagnostic_episodes"], [])
        self.assertIsNone(missing["diagnostic_unrecovered_count"])
        self.assertFalse(missing["diagnostic_evidence_available"])
        missing = ev.recovery_metrics(c, spec=spec, audit=[{"phase": "complete", "toolCallId": "1"}])
        self.assertIsNone(missing["diagnostic_unrecovered_count"])

    def test_identity_not_tool_name_and_search_separate(self):
        c = calls(tool("1"), tool("2", "code_search"))
        condition = {"extension_revision": "rev", "expected_activation": {"wrapper_tools": ["read"]}}
        self.assertIsNone(ev.verify_activation(c, condition=condition, audit=None)["wrapper_execution_counts"])
        audit = [{"toolCallId": "1", "tool": "read", "implementation_id": "kernel/read", "revision": "rev",
                  "phase": phase, "success": True} for phase in ("enter", "complete")]
        m = ev.verify_activation(c, condition=condition, audit=audit)
        self.assertEqual(m["activation_status"], "verified")
        self.assertEqual(m["code_search_calls"], 1)
        self.assertEqual(m["code_search_wrapper_executions"], 0)
        self.assertEqual(ev.verify_activation(c, condition=condition, audit=audit[1:])["activation_status"], "contradicted")

    def test_offline_pinned_tokenizer_distribution(self):
        class Tokenizer:
            identity = "test-char-tokenizer@1"
            def encode(self, text):
                return list(text)
        c = calls(tool("1", text="a"), tool("2", text="abc"))
        m = ev.response_metrics(c, tokenizer=Tokenizer())
        self.assertEqual(m["tool_response_tokens_est_distribution"]["median"], 2)
        self.assertEqual(m["tool_response_tokens_est_distribution"]["p95"], 3)
        with self.assertRaises(ValueError):
            ev.response_metrics(c, tokenizer=object())

    def test_unexecuted_request_is_not_an_executed_tool_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            event = assistant([{"type": "toolCall", "id": "pending", "name": "code_search", "arguments": {"query": "x"}}])
            (directory / "stdout.jsonl").write_text(json.dumps(event))
            m = ev.parse_run(directory)
            self.assertEqual(m["tool_calls_requested"], 1)
            self.assertEqual(m["tool_calls_total"], 0)
            self.assertEqual(m["code_search_calls"], 0)
            self.assertEqual(m["code_search_requested_calls"], 1)
            self.assertEqual(len(ev.load_events(directory / "tool_metrics.jsonl")), 1)

    def test_usage_and_per_call_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = pathlib.Path(tmp)
            events = [assistant(usage={"input": 10, "output": 2, "cacheRead": 3, "cacheWrite": 4,
                                       "totalTokens": 19, "cost": {"total": .1}})] + tool("1", text="é")
            (directory / "stdout.jsonl").write_text("bad json\n" + "\n".join(map(json.dumps, events)))
            m = ev.parse_run(directory)
            self.assertEqual(m["total_tokens"], 19)
            self.assertEqual(m["cost_usd"], .1)
            self.assertTrue(m["pricing_complete"])
            evidence = ev.load_events(directory / "tool_metrics.jsonl")
            self.assertEqual(evidence[0]["tool_response_text_bytes"], 2)
            self.assertNotIn("text", evidence[0])

    def test_empty_or_missing_declared_conditions_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "run").mkdir()
            arguments = ["--results", tmp, "--references", tmp, "--label", "run"]
            self.assertEqual(ev.main(arguments), 1)
            manifest = root / "conditions.json"
            manifest.write_text(json.dumps({"conditions": [{"id": "absent"}]}))
            self.assertEqual(ev.main(arguments + ["--conditions", str(manifest)]), 1)

    def test_garbage_trace_cannot_be_a_scored_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            cell = root / "run/custom/task"
            cell.mkdir(parents=True)
            ref = root / "refs/task"
            ref.mkdir(parents=True)
            (ref / "reference.json").write_text(json.dumps({"scoring": {"absence": {"none_of": ["wrong"]}}}))
            (cell / "stdout.jsonl").write_text("garbage\n")
            (cell / "exit_code").write_text("0")
            (cell / "wall_seconds").write_text("garbage")
            self.assertEqual(ev.main(["--results", tmp, "--references", str(root / "refs"), "--label", "run"]), 1)
            row = json.loads((cell / "metrics.json").read_text())
            self.assertEqual(row["cell_status"], "infra_invalid")
            self.assertIn("no completed", row["invalid_reason"])

    def test_manifest_discovery_retains_invalid_cost_and_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            refs = root / "refs"
            refs.mkdir()
            manifest = root / "conditions.json"
            manifest.write_text(json.dumps({"conditions": [{"id": "custom"}]}))
            for task, code in (("bad", 1), ("timeout", 124)):
                cell = root / "run" / "custom" / task
                cell.mkdir(parents=True)
                (cell / "stdout.jsonl").write_text(json.dumps(assistant(usage={"totalTokens": 50})))
                (cell / "exit_code").write_text(str(code))
                if task == "timeout":
                    (cell / "termination.json").write_text(json.dumps({"reason": "wall_limit"}))
            self.assertEqual(ev.main(["--results", tmp, "--references", str(refs), "--label", "run",
                                      "--conditions", str(manifest)]), 1)
            rows = ev.load_events(root / "run" / "summary.jsonl")
            self.assertEqual([r["cell_status"] for r in rows], ["infra_invalid", "valid_failure"])
            self.assertEqual(sum(r["total_tokens"] for r in rows), 100)


if __name__ == "__main__":
    unittest.main()
