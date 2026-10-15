import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import verify_wrappers as vw
from conditions import pi_flags
from test_evaluate import tool


class WrapperTests(unittest.TestCase):
    def condition(self):
        return {"extension": "/kernel.ts", "extension_revision": "rev", "tools": ["read", "edit", "code_search"],
                "guidance_file": None, "instrumentation": {"revision": "rev", "patch_sha256": "reviewed-hash",
                                                          "execute_locations": ["source-reviewed execute functions"]},
                "expected_activation": {"wrapper_tools": ["read", "edit"], "settings": {"compression": True, "retrieval": True},
                                        "wrapper_implementations": {t: "kernel/" + t for t in ("read", "edit", "code_search")}}}

    def capture(self, root):
        events, audit = [], []
        for name in ("read", "edit", "code_search"):
            events += tool(name, name=name, text="post")
            base = {"toolCallId": name, "tool": name, "implementation_id": "kernel/" + name, "revision": "rev"}
            audit += [{**base, "phase": "enter"}, {**base, "phase": "complete", "success": True,
                       "settings": {"compression": True, "retrieval": True},
                       "pre_text": "before", "post_text": "post", "pre_text_bytes": 6, "post_text_bytes": 4,
                       "pre_sha256": vw.sha("before"), "post_sha256": vw.sha("post"), "compression_changed": True}]
        (root / "stdout.jsonl").write_text("\n".join(map(json.dumps, events)))
        (root / "wrapper_audit.jsonl").write_text("\n".join(map(json.dumps, audit)))
        return audit

    def test_names_and_loading_do_not_prove_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "stdout.jsonl").write_text("\n".join(map(json.dumps, tool("read"))))
            result = vw.check_capture(root, self.condition())
            self.assertEqual(result["status"], "BLOCKED")
            self.assertIsNone(result["code_search_execution"])

    def test_valid_probe_and_real_cell_search_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.capture(root)
            c = self.condition()
            self.assertEqual(vw.check_capture(root, c)["status"], "verified")
            self.assertEqual(vw.check_capture(root, c)["code_search_execution"], 1)
            self.assertEqual(vw.check_capture(root, c, probe=True)["status"], "BLOCKED")
            (root / "probe_host.json").write_text(json.dumps({"network_mode": "none", "image_digest": "sha256:test",
                                                             "production_flags": pi_flags(c)}))
            self.assertEqual(vw.check_capture(root, c, probe=True)["status"], "verified")

    def test_hash_settings_and_delivered_output_reject_misleading_audit(self):
        for field, value in (("post_sha256", "wrong"), ("post_text", "not delivered"),
                             ("settings", {"compression": False, "retrieval": True})):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp)
                audit = self.capture(root)
                audit[1][field] = value
                (root / "wrapper_audit.jsonl").write_text("\n".join(map(json.dumps, audit)))
                result = vw.check_capture(root, self.condition())
                self.assertEqual(result["status"], "BLOCKED")
                self.assertTrue(result["audit_errors"])

    def test_missing_source_instrumentation_blocks_even_with_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.capture(root)
            c = self.condition()
            del c["instrumentation"]
            self.assertEqual(vw.check_capture(root, c)["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
