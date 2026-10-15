#!/usr/bin/env python3
"""Instrument a vendored pi-agent-kernel checkout for the retrieval-regression
experiment.

Adds two things, idempotently:
  1. A sidecar wrapper audit (`src/pi_audit.ts`) written to $KERNEL_AUDIT_PATH,
     recording per-call pre/post bytes and whether compression changed output.
  2. A `KERNEL_NO_COMPRESSION=1` bypass for the compression paths (bash clamp,
     read cap, code_search budget) used by condition C.

This is a versioned harness patch applied identically to B and C; the env var is
only set for C, so the two conditions differ only in compression.

Usage: harness/instrument_kernel.py <vendored-kernel-dir>
"""
from __future__ import annotations

import pathlib
import sys

AUDIT_TS = '''// Injected by agent-codeintel-bench (harness/instrument_kernel.py).
// Sidecar audit + compression bypass. Never alters model-visible output except
// when KERNEL_NO_COMPRESSION=1, which disables the compression paths.
import * as fs from "node:fs";

export function compressionDisabled(): boolean {
	return process.env.KERNEL_NO_COMPRESSION === "1";
}

export function audit(record: Record<string, unknown>): void {
	const target = process.env.KERNEL_AUDIT_PATH;
	if (!target) return;
	try {
		fs.appendFileSync(target, JSON.stringify({ ts: Date.now(), ...record }) + "\\n");
	} catch {
		// Auditing must never break a tool call.
	}
}
'''

IMPORT_LINE = 'import { audit, compressionDisabled } from "../pi_audit";\n'
IMPORT_LINE_ROOT = 'import { audit, compressionDisabled } from "./pi_audit";\n'


def edit(path: pathlib.Path, transform) -> None:
    text = path.read_text()
    new = transform(text)
    if new != text:
        path.write_text(new)
        print(f"  patched {path.name}")
    else:
        print(f"  unchanged {path.name}")


def prepend_import(rel: str):
    def transform(text: str) -> str:
        if "pi_audit" in text:
            return text
        return rel + text
    return transform


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    root = pathlib.Path(argv[0]).resolve()
    src = root / "src"
    if not (src / "index.ts").exists():
        print(f"error: not a pi-agent-kernel checkout: {root}", file=sys.stderr)
        return 2

    (src / "pi_audit.ts").write_text(AUDIT_TS)
    print("wrote src/pi_audit.ts")

    # 1. bash output clamp bypass + audit
    oc = src / "safety" / "output_clamper.ts"

    def do_oc(text: str) -> str:
        if "pi_audit" not in text:
            text = IMPORT_LINE + text
        anchor = "\tconst originalBytes = Buffer.byteLength(rawText, \"utf8\");\n"
        bypass = anchor + (
            "\tif (compressionDisabled()) {\n"
            "\t\tconst bytes = Buffer.byteLength(rawText, \"utf8\");\n"
            "\t\tconst lines = rawText.split(/\\r?\\n/).length;\n"
            "\t\taudit({ tool: \"bash\", wrapper: \"kernel.output_clamper\", originalBytes: bytes, returnedBytes: bytes, truncated: false, compression: \"disabled\" });\n"
            "\t\treturn { text: rawText, truncated: false, originalBytes: bytes, returnedBytes: bytes, totalLines: lines, shownLines: lines };\n"
            "\t}\n"
        )
        if "compressionDisabled()" not in text:
            if anchor not in text:
                raise SystemExit("anchor not found in output_clamper.ts")
            text = text.replace(anchor, bypass, 1)
        return text

    edit(oc, do_oc)

    # 2. read cap bypass + audit
    rt = src / "tools" / "read_tool.ts"

    def do_rt(text: str) -> str:
        if "pi_audit" not in text:
            text = IMPORT_LINE + text
        old = "\t\t\t\t\t\tconst visibleIndexes = selectReadLineIndexes(lines, startIdx, endIdx, formatLine);\n"
        new = (
            "\t\t\t\t\t\tconst visibleIndexes = compressionDisabled()\n"
            "\t\t\t\t\t\t\t? Array.from({ length: Math.max(0, endIdx - startIdx) }, (_, i) => startIdx + i)\n"
            "\t\t\t\t\t\t\t: selectReadLineIndexes(lines, startIdx, endIdx, formatLine);\n"
        )
        if "compressionDisabled()" not in text:
            if old not in text:
                raise SystemExit("anchor not found in read_tool.ts (visibleIndexes)")
            text = text.replace(old, new, 1)
        old2 = "\t\t\t\tconst isTruncated = oversizedFirstLine || hasMore || startIdx > 0;\n"
        new2 = old2 + (
            "\t\t\t\taudit({ tool: \"read\", wrapper: \"kernel.read_tool\", totalLines, shownLines: visibleIndexes.length, truncated: isTruncated, compression: compressionDisabled() ? \"disabled\" : \"enabled\" });\n"
        )
        if 'tool: "read"' not in text:
            if old2 not in text:
                raise SystemExit("anchor not found in read_tool.ts (isTruncated)")
            text = text.replace(old2, new2, 1)
        return text

    edit(rt, do_rt)

    # 3. code_search output budget bypass
    cs = src / "tools" / "code_search_output.ts"

    def do_cs(text: str) -> str:
        if "pi_audit" not in text:
            text = IMPORT_LINE + text
        anchor = "function clipToBudget(text: string, budget: number): string {\n"
        bypass = anchor + "\tif (compressionDisabled()) {\n\t\taudit({ tool: \"code_search\", wrapper: \"kernel.code_search_output\", budget, compression: \"disabled\" });\n\t\treturn text;\n\t}\n"
        if "compressionDisabled()" not in text:
            if anchor not in text:
                raise SystemExit("anchor not found in code_search_output.ts")
            text = text.replace(anchor, bypass, 1)
        return text

    edit(cs, do_cs)

    # 4. wrapper audit for the bash output hook (the compression path under test).
    #    Full check_capture schema: settings, pre/post text + hashes.
    ix = src / "index.ts"

    def do_ix(text: str) -> str:
        if "pi_audit" not in text:
            text = IMPORT_LINE_ROOT + text
        call_anchor = '\tpi.on("tool_call", async (event: any, ctx: any) => {\n'
        enter = call_anchor + (
            '\t\tif (event?.toolName === "bash") audit({ phase: "enter", toolCallId: event?.toolCallId, '
            'tool: "bash", implementation_id: "kernel.bash", revision: "b9e93be" });\n'
        )
        if 'phase: "enter"' not in text:
            if call_anchor not in text:
                raise SystemExit("anchor not found in index.ts (tool_call)")
            text = text.replace(call_anchor, enter, 1)
        anchor = ("\t\t\tif (event.isError) {\n\t\t\t\treturn resultContent !== undefined\n"
                  "\t\t\t\t\t? { content: resultContent, isError: true }\n\t\t\t\t\t: undefined;\n\t\t\t}\n")
        complete = anchor + (
            '\t\t\tconst __joinText = (blocks: any): string => (blocks || []).filter((b: any) => b && b.type === "text" && typeof b.text === "string").map((b: any) => b.text).join("");\n'
            '\t\t\tconst __pre = __joinText(event.content);\n'
            '\t\t\tconst __post = __joinText(resultContent !== undefined ? resultContent : event.content);\n'
            '\t\t\tconst __sha = (t: string): string => createHash("sha256").update(t).digest("hex");\n'
            '\t\t\taudit({ phase: "complete", toolCallId: event?.toolCallId, tool: "bash", '
            'implementation_id: "kernel.bash", revision: "b9e93be", success: !event.isError, '
            'settings: { compression: compressionDisabled() ? "disabled" : "enabled", retrieval: "enabled" }, '
            'pre_text: __pre, post_text: __post, '
            'pre_text_bytes: Buffer.byteLength(__pre, "utf8"), pre_sha256: __sha(__pre), '
            'post_text_bytes: Buffer.byteLength(__post, "utf8"), post_sha256: __sha(__post), '
            'compression_changed: __pre !== __post });\n'
        )
        if 'phase: "complete"' not in text:
            if anchor not in text:
                raise SystemExit("anchor not found in index.ts (bash isError block)")
            text = text.replace(anchor, complete, 1)
        # createHash import for the audit hashes
        if 'node:crypto' not in text:
            text = text.replace(IMPORT_LINE_ROOT, IMPORT_LINE_ROOT + 'import { createHash } from "node:crypto";\n', 1)
        return text

    edit(ix, do_ix)

    print("instrumentation complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
