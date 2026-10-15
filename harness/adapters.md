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

## Tools that need dependencies or downloaded models

If the tool is not self-contained, bake it into a per-tool image so the run stays
offline (see `docker/README.md` → "Tools with dependencies or downloaded
models"):

```bash
docker/run.sh tool /path/to/tool
source work/tool.env
```

`provision.sh` (build-time setup) and `warmup.sh` (model download) are optional
hooks inside the tool directory.

## Kernel retrieval experiment — source-dependent BLOCKED items

`experiments/kernel-retrieval.json` is a **draft, not a frozen treatment**.
Reports 0003–0004 pin Kernel `b9e93be` / v0.4.0, **lean**. No pinned Kernel
source, instrumented image, raw container Pi trace or tokenizer assets are
supplied in this repository. Do not infer “fully enabled” from those reports.

- **B BLOCKED:** inspect that exact revision, expand the full revision hash,
  establish the actual full configuration and add identical B/C execute-function
  instrumentation before clearing `blocked_reason`.
- **C BLOCKED:** no independent supported compression switch has been verified.
  Inspect read clamping, search compaction, edit-result shaping, any shell
  shaping, and context hooks. Do not invent an environment flag. A versioned
  bypass patch is a separate treatment, not a supported upstream ablation.
- **Compatibility BLOCKED:** validate raw event normalization against Pi 1.2.0
  from the actual container. Synthetic unit traces do not establish compatibility.
- **Exposure/pilots BLOCKED:** validate diagnostic pre/post visibility and real
  multi-cycle inspect/edit/test traces before freezing tasks or starting trials.

All compression/retrieval labels are declarations, not Kernel settings. To unblock
C, the manifest requires `compression_control.verified`, exact `revision`,
`source_evidence`, allowed `env_keys` and (if needed) `config_files_verified`.
These fields document a source review; they are not automatic proof of it.
`config_file` is hashed and checked, not translated into a guessed extension flag;
use only source-verified native configuration bindings in the declared `env`.
Extension entry, guidance/config and prompt hashes are recorded in runtime
metadata; image IDs, corpus tree hash, model, tools, limits and condition config
are recorded per cell. An extension-entry hash is NOT a full source/patch hash:
supply reviewed `extension_revision_evidence` and patch hash when available.

Set `CONDITIONS_FILE=$PWD/experiments/kernel-retrieval.json` for manifest mode.
The isolated runner uses ABC, BCA, CAB, ACB, CBA, BAC sequentially (3-trial pilot
or 6-trial run). Existing A/B mode remains available without a manifest. Every
cell gets only its own writable `/out`; there is no Compose default result
mount. Hidden tests, references and metrics specs never enter the agent container.
A/B/C use the same declared tool image, with Kernel unloaded in A. Missing
images are blocked; orchestration uses local images (`--pull never`). Scoring
uses one trusted `SCORING_IMAGE` (defaults to A's image), never each arm's image.
Snapshot commit dates are deterministic. Do not reuse a nonempty cell directory.

`run_condition.sh` also resolves the manifest, using its preprepared per-condition
workspace. It is a local runner, **not** a sandbox; use `run_isolated.sh` for
untrusted tools. `run_cell.py` shares the exact production flags, clears ambient
treatment environment (even unknown Kernel keys), and applies only declared env
plus runtime/model/cache essentials. Declare required dependency settings rather
than relying on global exports. Native Pi truncation/compaction flags are not
changed. Wall time and output limits apply equally, retain terminated output and
record termination; combined-output polling can overshoot briefly, with a hard
per-file cap. All attempted costs remain in summaries, including failures.

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
