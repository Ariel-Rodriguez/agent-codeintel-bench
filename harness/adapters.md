# Adding a code-intelligence tool

The harness treats "enhanced" as *baseline plus one tool*. A tool is any Pi
extension, MCP server, or custom tool set that adds structural code intelligence
(symbols, call graphs, references, impact). The only contract is the two env
values read by `harness/run_condition.sh`:

| env | meaning |
|---|---|
| `ENHANCED_TOOLS` | comma-separated `--tools` list for the enhanced arm, e.g. `read,bash,edit,write,codeindex_*` |
| `CODEINTEL_EXT` | path passed to `pi -e <path>` for the enhanced arm (leave empty for MCP/tool-only integrations) |

Baseline always uses `read,bash,edit,write` unless you override `BASELINE_TOOLS`.
Everything else — prompt, tasks, scoring, fixture — stays fixed, which keeps the
comparison to "added code intelligence only".

## Tool #1: `pi-codeindex` (structural index)

```bash
export ENHANCED_TOOLS='read,bash,edit,write,codeindex_*'
export CODEINTEL_EXT="$PWD/vendor/pi-codeindex/src/pi/index.ts"
harness/prepare.sh
harness/run_suite.sh run1
harness/evaluate.py run1
```

Vendor the tool under `vendor/` (gitignored) or point `CODEINTEL_EXT` at an
installed copy. Pin the exact revision you tested and write it down — results are
valid only for that revision.

## Tools worth adding next

- LSP-backed symbol tools (e.g. a language-server bridge)
- AST/embedding search (e.g. tree-sitter + BM25/bm25 hybrids)
- call-graph / SCIP export + import
- MCP servers exposing `find_references`, `go_to_definition`, `incoming_calls`

## Fairness rules

1. Only the enhanced arm may load the tool; baseline must not.
2. Both arms use the same prompts, fixture commit, model, thinking level, and
   tool budget for built-ins.
3. Verify the tool was actually visible and executed (parse the system prompt and
   `tool_execution_*` events in `results/*/stdout.jsonl`); "the tool is
   installed" is not evidence that it was used.
4. Record the tool revision and any local patch separately; a patched tool is a
   different treatment from the upstream release.
5. Re-run each task at least 3 times, counterbalanced, sequentially. Model
   nondeterminism and provider caching dominate at n=1.
