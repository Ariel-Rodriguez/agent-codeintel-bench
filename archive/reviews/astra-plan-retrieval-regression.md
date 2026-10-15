# Design — astra (openai/gpt-6-astra, medium)

- Date: 2026-10-15
- Question: design an implementation plan to detect a tool that reduces per-operation context but degrades long-horizon efficiency (Reddit-derived hypothesis).
- Read-only design; implementation by sol xhigh.

---

## Findings and limits

Read `harness/evaluate.py`, both runners, Docker entrypoint/isolation, repair scorer, fixtures, and Agent Kernel reports 0003–0004.

- The isolated experiment actually executes **`docker/entrypoint.sh:run_one()`**, not `harness/run_condition.sh`. Both need compatible condition handling.
- `evaluate.py:main()` hardcodes `baseline/enhanced`; `parse_run()` ignores tool arguments/results.
- No raw JSONL traces or Agent Kernel source are checked in. Reports pin `b9e93be`, **lean** profile—not necessarily “fully enabled.” Compression configuration must be verified against the supplied extension revision; do not invent a disable flag.
- Existing traces can establish repetition and delivered output size. They cannot, in general, establish **what compression removed, whether a wrapper executed, or causally attributable recovery calls** without additional evidence.

## 1. Metrics and evaluator interfaces

### Event normalization

Join:

- `tool_execution_start`: `toolCallId`, `toolName`, `args`.
- `tool_execution_end`: `toolCallId`, `result.content`, `result.details`, `isError`, optional `durationMs`.
- `message_end`: `message.role`, `message.content`; assistant blocks with `type="toolCall"`, `id`, `name`, `arguments` provide a fallback argument source.
- Prefer completed `message.role="toolResult"` content, joined through `message.toolCallId`, for model-visible text; otherwise use `result.content`. Record which source was used; never count both.
- Define a **turn** as one completed assistant `message_end`, not a tool call. Preserve event ordering and call IDs.

Validate this schema against traces from the **pinned container Pi version** before measuring.

### Exact metric names

| Metric | Computation |
|---|---|
| `repeat_file_read_calls` | For successful `read` calls, normalize `args.path` relative to workspace; count every read after the first of that path. |
| `repeat_read_range_calls` | Count repeated keys `(path, args.offset or 1, args.limit or DEFAULT)`. Keep omitted limit as a distinct default; do not assume it means EOF. |
| `overlap_read_requested_lines` | For explicitly bounded read ranges, sum overlap with the union of earlier requested intervals for that path. Report bounded-range coverage separately. This measures requested overlap, not necessarily returned lines. |
| `repeat_bash_command_calls` | Count repeated `args.command` strings after the first, stripping only outer whitespace. Do not normalize quoting or reorder shell syntax. Workspace is fixed; embedded `cd` remains part of the command. |
| `tool_response_text_bytes` | Per-call UTF-8 byte count of delivered text blocks, plus total and by-tool summaries. Exclude metadata not sent to the model. |
| `tool_response_tokens_est` | Per-call tokenization of that same text using a pinned, offline tokenizer; report mean, median, p95, total, and by-tool values. Label as an estimate: provider framing and billed tokens are not available per response. Null if no suitable tokenizer exists. |
| `truncated_tool_responses` | Count explicit truncation evidence in `result.details` or version-pinned output markers; save evidence and source. Missing metadata means **unknown**, not “not truncated.” |
| `post_truncation_retrieval_calls` | Within the next five assistant turns, count distinct calls that revisit the truncated file/range or repeat/refine the producing command. Match simple shell forms conservatively; store linked call IDs and match reason. This is an association, not causal attribution. |
| `post_truncation_repeat_read_calls` | Subset above that repeats/overlaps an earlier read. |
| `diagnostic_recovery_turns` | Per diagnostic episode: assistant-turn index when a diagnostic first reappears in delivered output minus index of the result known to have omitted it. Requires evidence that the omitted result contained the diagnostic before compression. |
| `diagnostic_unrecovered_count` | Number of established omission episodes without later recovery; retain right-censored episodes rather than dropping them from averages. |
| `wrapper_execution_counts` | Executed calls grouped by verified wrapper implementation ID—not by tool name alone. Unknown for old traces without execution evidence. |

Repeated reads/test commands can be legitimate after edits. Retain raw counts, but split repetition into **intervening mutation / no intervening mutation / unknown**, using successful `edit`, `write`, and conservatively classified shell calls. Report rerun tests separately from retrieval commands.

Keep existing `message.usage.input/output/cacheRead/cacheWrite/totalTokens/cost.total` accounting. Per-response text tokens are **not** additional billable tokens.

### Proposed signatures in `harness/evaluate.py`

```python
def load_events(stream: pathlib.Path) -> list[dict]: ...
def normalize_tool_calls(events: list[dict]) -> list[dict]: ...
def retrieval_metrics(calls: list[dict], *, spec: dict) -> dict: ...
def response_metrics(calls: list[dict], *, tokenizer) -> dict: ...
def recovery_metrics(calls: list[dict], *, spec: dict,
                     audit: list[dict] | None) -> dict: ...
def verify_activation(calls: list[dict], *, condition: dict,
                      audit: list[dict] | None) -> dict: ...
def parse_run(directory: pathlib.Path, *, spec: dict | None = None,
              tokenizer=None, condition: dict | None = None) -> dict: ...
```

Write per-call evidence to `tool_metrics.jsonl`; aggregates to `metrics.json`. Extend `write_csv()` with scalar aggregates; preserve episodes and distributions in JSON. Replace hardcoded arm discovery with the declared condition manifest.

## 2. Runner and compression ablation

Add host-side `experiments/kernel-retrieval.json`, selected by proposed `CONDITIONS_FILE`.

| Condition ID | Extension | Guidance | Compression | Retrieval |
|---|---|---|---|---|
| `baseline` — A | None | None | Vanilla Pi behavior | Built-ins |
| `kernel_full` — B | Pinned Kernel entry | Pinned `GUIDANCE_FILE` | Enabled | Enabled |
| `kernel_no_compression` — C | Same entry/revision | **Identical to B** | Disabled | Identical to B |

Manifest fields: `id`, `image`, `extension`, `tools`, `guidance_file`, `env`, `config_file`, `expected_activation`. Compression/retrieval labels are **harness declarations**, not presumed Kernel environment variables.

Implementation requirements:

- Resolve each manifest entry independently; no global environment leakage between cells.
- B/C use the same per-tool image and profile, differing only in verified compression controls. Prefer using that same image for A too, with Kernel unloaded, to eliminate dependency-image differences.
- Translate C into the extension’s **actual supported configuration** after inspecting its source. Enumerate all output-shaping paths: read clamping, search compaction, edit-result shaping, shell shaping if present, and context hooks.
- Keep Pi’s native truncation/compaction settings unchanged across A/B/C.
- If no independent switch exists, **C is blocked**. An explicitly versioned, minimal compression-bypass patch is an optional separate treatment, not an upstream-supported ablation.
- Record effective configuration, image digest, extension revision/patch hash, guidance hash, model settings, tool list, prompt hash, corpus tree hash, and limits in each cell. Current synthetic commits have variable timestamps; make snapshot commit metadata deterministic if comparing commit IDs.
- Enforce equal wall/output budgets and record limit termination. Do not silently discard expensive failed attempts.

Use six sequential trials: **ABC, BCA, CAB, ACB, CBA, BAC**. This balances positions and pairwise order, with n=6 per condition. Three cyclic trials are the minimum position-balanced pilot.

Maintain `/out/<run>-tN/<condition>/<task>/` as the only writable result mount. Remove the broad default `../out:/out` mount from the isolated service path rather than relying on mount replacement.

## 3. Task: `repair_retrieval_long`

Extend the public `fixtures/widget-service/` corpus with a deterministic, substantive integration flow:

1. Route parses observation timestamps and identifiers.
2. Freshness logic validates finite timestamps, units, and boundaries.
3. Transaction reducer handles replay/idempotency.
4. Operation log records refusals and successful transitions.

Introduce a coordinated regression in **three production files**: timestamp-unit normalization, replay identity handling, and terminal-state/log handling. Hidden tests must independently detect each defect so a one-line bypass cannot pass.

Add:

- `benchmarks/repair_retrieval_long/prompt.md`: symptom-only description; require initial full-suite execution, repair, focused checks, then full-suite rerun. Do not prescribe retrieval strategy.
- `fixture.patch`: bugs plus public regression tests and a deterministic verbose suite runner.
- `verify.json`: trusted full-suite command, hidden invariants, test-change rejection.
- `metrics.json`: host-only diagnostic definitions and recovery matching rules.

**Long-output mechanism:** the public runner emits real scenario traces surrounding failures. Place a meaningful diagnostic such as `OBS_TS_UNIT_MISMATCH` in the middle of a failing trace; ordinary summary identifies failure without repeating that diagnostic. A focused test invocation exposes it again.

Pilot output length against actual B/C behavior: the diagnostic must be visible before Kernel compression and absent afterward, while avoiding a case where vanilla Pi drops it too. If that cannot be achieved, use a long source-read diagnostic as the primary compression exposure and keep the verbose suite as shell-overhead stress. Do not assume Kernel wraps `bash`; reports only establish registration of `read`, `edit`, and `code_search`.

Also add `repair_retrieval_small`: one localized defect in the same corpus, short output, same conditions. This measures startup/tool-guidance overhead without conflating it with long-horizon recovery.

Host-only validation before trials:

- Broken fixture fails expected checks.
- Reference repair passes everything.
- Partial fixes and bypasses fail.
- Diagnostic visibility differs as intended under B/C.
- Pilot traces actually contain multiple inspect–edit–test cycles; otherwise redesign before freezing the benchmark.

## 4. Decision rules

Pre-register a practical effect threshold, for example **10%**, and report paired trial differences and every cell. n=3–6 is exploratory, not strong statistical confirmation.

Report three separate outcomes:

1. **Correctness:** verified successes / attempted valid cells.
2. **Resource consumption:** cost, cumulative tokens, wall time, calls—including failed attempts.
3. **Efficiency:** `sum(successes) / sum(execution_cost_usd)`.

If model pricing is missing/zero, USD efficiency is **undefined**, not infinite. Use separately named successes per million accounted tokens and per execution hour.

Evidence supporting the hypothesis:

- B delivers smaller comparable tool responses than C/A;
- B has greater long-task total cost or lower successful-tasks-per-cost;
- B has more repeated retrieval/recovery episodes;
- C mitigates the regression at comparable correctness.

B versus C is the compression contrast; B versus A also changes retrieval and guidance. Compare response sizes by tool and matched operation—not only a pooled average vulnerable to changing call mix.

Evidence against it **for this task/model**: verified compression exposure, equal-or-better correctness, lower response size, and no material long-task cost/recovery penalty. Missing compression exposure, inactive wrappers, unsupported C, or mixed small-sample results are **inconclusive**.

Never call a cheaper arm superior if correctness deteriorates. Present the correctness–cost tradeoff explicitly; do not use success-only cost averages as the primary comparison.

## 5. Prove wrapper execution

`toolName="read"` and successful extension loading do not identify the implementation.

Add a minimal audit path inside the **actual Kernel wrapper execute functions**, emitting a sidecar record:

- `toolCallId`, tool name, wrapper implementation/revision;
- entry and successful/failed completion;
- effective compression/retrieval settings;
- pre-/post-compression text byte counts and hashes;
- whether compression changed output;
- diagnostic-presence evidence when available.

Keep audit data out of model-visible tool content. Compute diagnostic matches host-side from captured pre-/post-output; do not give the agent hidden diagnostic specifications. Label any instrumentation patch and apply it identically to B/C.

Add an offline compatibility probe using the exact production flags, including `--no-extensions -e ... --tools ...`. Exercise built-in-name `read`/`edit` wrappers and retrieval on a harmless fixture; confirm execution reaches Kernel code and behavior changes appropriately under C.

For real cells, join audit records to JSONL call IDs. Require actual wrapper execution, not just the probe. Report `code_search` execution separately; retrieval being registered is not retrieval being used.

Old results without this evidence cannot establish that savings came from wrappers.

## 6. Ordered implementation and run commands

1. **Inspect/pin Kernel**, establish supported configuration and wrapper locations; document in `harness/adapters.md`. Block unsupported C explicitly.
2. **Create fixtures/tasks** above; extend `harness/score_repair.py:main()` to overlay trusted hidden tests after reconstruction and reject tampering through both patches and untracked files. Use one trusted scoring image for all conditions, with `--network none`.
3. **Implement manifest orchestration** in `harness/run_isolated.sh:run_one()`, `docker/entrypoint.sh:run_one()`, and `harness/run_condition.sh`; update `docker/compose.yaml` isolation and limits.
4. **Add wrapper audit/probe**, proposed `harness/verify_wrappers.py:main(argv=None) -> int`; retain load probing separately.
5. **Implement evaluator signatures/metrics**, condition discovery, censored recovery, and missing-evidence handling. Add synthetic JSONL tests under `harness/tests/test_evaluate.py`.
6. **Aggregate outcomes**, proposed `harness/summarize_experiment.py:main(argv=None) -> int`. Keep infrastructure-invalid cells distinct from valid task failures/timeouts, and report their resource costs separately.
7. Run offline fixture/probe validation, excluded pilots, freeze manifest, then counterbalanced trials.

**Proposed commands after implementation**—not currently supported end-to-end:

```bash
# Provision beforehand from pinned local sources/caches.
docker/run.sh build
docker/run.sh tool /path/to/pinned/pi-agent-kernel agent-kernel
source work/tool.env

export CONDITIONS_FILE="$PWD/experiments/kernel-retrieval.json"
export CORPUS="$PWD/fixtures/widget-service" TASKS="$PWD/benchmarks"
export PI_PROVIDER=<provider> PI_MODEL=<model> PI_THINKING=medium
export UPSTREAM_BASE_URL=<allowlisted-model-origin>

python3 -m unittest discover -s harness/tests
python3 harness/verify_wrappers.py --conditions "$CONDITIONS_FILE"

RUN_ID=kernel-retrieval TRIALS=6 \
TASK_LIST="repair_retrieval_long repair_retrieval_small" \
harness/run_isolated.sh

python3 harness/summarize_experiment.py \
  --results out --run-id kernel-retrieval
```

All runtime dependencies/tokenizers are baked beforehand. Agents retain only the existing allowlisted model gateway—no arbitrary network egress; probes and scoring run with no network. References, hidden tests, and scoring specifications remain host-side.
