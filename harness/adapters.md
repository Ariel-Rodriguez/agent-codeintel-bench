# Adding a code-intelligence tool

For new candidate evaluations prefer the manifest-based
[dual-baseline workflow](../docs/dual-baseline.md): scientific and adoption pairs,
frozen sanitized baselines, explicit inheritance and execution proof. The
candidate alone changes within each pair; a personal baseline may already load
other pinned extensions. The two-arm adapter below remains supported.

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

## Kernel retrieval experiment — source-dependent requirements

`experiments/kernel-retrieval.json` now freezes Kernel `b9e93be` / v0.4.0,
**lean**, with the versioned `harness/instrument_kernel.py` patch. Report 0005
supersedes the earlier draft-blocked status: its A/B/C pilot captured verified
wrapper execution and the compression contrast. The bypass is a reviewed local
patch, **not** a supported upstream switch. Raw traces and provisioned images are
not guaranteed to be present in a fresh checkout.

For a new run, inspect the pinned source, apply identical B/C instrumentation,
provision images explicitly, and capture production compatibility/execution
proof again. Missing prerequisites remain blocked. Synthetic unit traces do not
establish real Pi compatibility, exposure, or performance. The single repeated
read and zero post-truncation retrieval events in the pilot do not establish
repeated retrieval as the primary mechanism of its observed token regression.

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
B/C use the same declared tool image; A uses `BASE_IMAGE` without Kernel. Missing
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

### Execute audit contract and offline verification

`python3 harness/verify_wrappers.py --conditions experiments/kernel-retrieval.json`
without `--cell` exits **2 / BLOCKED**, not success: declarations are not captured
evidence. Apply the existing instrumentation to the pinned source and capture a
real probe before claiming compatibility. `probe_load.mjs`
continues to prove only import/registration and is intentionally separate.

The host verifier accepts `--condition-id ID --cell DIR` (add `--probe` for a
captured compatibility probe). It requires paired records with `phase: enter`
and `phase: complete`, `toolCallId`, `tool`, `implementation_id`, `revision`,
boolean `success`, and completion `settings: {compression, retrieval}`. Completion
must capture `pre_text`, `post_text`, their `pre_text_bytes`/`post_text_bytes`,
`pre_sha256`/`post_sha256` (UTF-8 text only), and `compression_changed`. Sidecars
must never be returned in tool content. Keep diagnostic specifications host-side;
match them against captured output only after the run.

Source review must populate the condition's `instrumentation` (`revision`,
`patch_sha256`, `execute_locations`) and `expected_activation`:
`wrapper_implementations` maps tool names to reviewed implementation IDs;
`settings` specifies effective settings. Apply the identical instrumentation patch
to B/C. The verifier checks hashes, settings, visible output and joined execution;
it does not claim to authenticate arbitrary agent-writable audit files. Use a
trusted capture path/instrumentation when producing real evidence.

A probe also needs host-created `probe_host.json` with `network_mode: none`,
`image_digest` and `production_flags` equal to `conditions.pi_flags(condition)`.
Exercise harmless read/edit/search calls in the exact production invocation,
including `--no-extensions -e ENTRY --tools LIST`; a custom direct-call mock is
not a production compatibility probe. Both built-in-name wrappers and
`code_search` must execute. Real cells require their own evidence (search use is
reported separately, not required just because it was registered in the probe).
A fresh dynamic no-network production probe and B/C behavior contrast require
the pinned source/instrumented image and new captures; no alternate mock probe
is presented as proof. Synthetic verifier tests test the host contract only.

### Host-only repair materials

Rebuild both base/tool images after these harness changes. `.dockerignore` now
excludes the unbroken fixture, benchmarks, hidden tests, reference generation,
host scoring and host tests; an old image may still contain those materials.
The host stages `corpus + fixture.patch` **before** mounting `/corpus`, without
source history. Otherwise an agent could recover the unbroken code by reading
the original `/corpus` mount even when the workspace had the regression.
Only this public broken snapshot, prompt and resolved condition enter a cell.

`score_repair.py` rejects protected files/config changes by comparing actual
reconstructed content, not only patch paths. This catches untracked test
injection/overwrites as well. Archive traversal, links and executable-environment
artifacts are rejected. New retrieval tasks permit changes only below `src/`.
Trusted hidden tests are overlaid only after tamper checks; they are never
mounted during agent execution. Verification uses a single trusted image with
`--network none --pull never`, resource limits and an offline venv. Infrastructure
errors stay distinct from failed repairs. The scorer cannot authenticate a
malicious sidecar or make arbitrary Python source safe outside its sandbox.

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
