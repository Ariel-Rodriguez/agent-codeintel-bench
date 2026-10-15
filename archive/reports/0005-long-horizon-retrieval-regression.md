# Report 0005 — Long-horizon retrieval regression (A/B/C pilot)

- **Status:** concluded (pilot; 3 trials, one task, one model)
- **Tool under test:** `floydous/pi-agent-kernel` @ `b9e93be` (v0.4.0, `lean`)
  plus a versioned harness instrumentation patch
  (`KERNEL_NO_COMPRESSION` bypass + wrapper audit; patch sha
  `9538a37c…`), applied identically to B and C
- **Model:** local `Qwen3.8-27B IQ3_S, 224k context`, thinking `medium`
- **Corpus/task:** the public `widget-service` fixture, `repair_retrieval_long`
- **Isolation:** fresh container per cell, sequential, no network egress,
  host-side executable scoring

This tests the hypothesis raised by the Reddit discussion: **can a tool reduce
context per operation while making the agent less efficient overall?**

## 1. Hypothesis

- **H1:** output compression reduces per-call response size but **increases
  long-horizon total cost** (tokens, wall) by causing repeated retrieval.
- **H0:** compression reduces cost without a long-horizon penalty.
- Correctness is measured separately so a cheaper failed run cannot look better.

## 2. Method

Three conditions on the same corpus, task, model and limits:

| condition | extension | compression | retrieval |
|---|---|---|---|
| `baseline` (A) | none | native Pi | built-ins |
| `kernel_full` (B) | kernel + instrumentation | **on** | on |
| `kernel_no_compression` (C) | identical extension/patch | **off** (`KERNEL_NO_COMPRESSION=1`) | on |

Sequential, counterbalanced order (ABC/BCA/CAB), one fresh container per cell,
cell-only output mount. Repair scored by a **trusted executable test** host-side.
Wrapper execution **verified** from an in-container audit sidecar: enter/complete
records joined by `toolCallId`, with `implementation_id`, revision, effective
settings, and pre/post text hashes — not inferred from tool names.

## 3. Materials

- Tool revision `b9e93be`; instrumentation patch adds the C bypass and the audit.
- B/C report `activation_status: verified` and `wrapper_proof: verified` in every
  cell. The toggle demonstrably changed behavior: B recorded `compression:
  enabled` with outputs actually changed; C recorded `disabled` with none changed.
- Public `widget-service` fixture and the `repair_retrieval_long` task.

## 4. Evidence

3 valid cells per condition, all repaired correctly.

| condition | correctness | total tokens | tool-response bytes | wall s | repeat reads | post-truncation retrieval |
|---|---|---|---|---|---|---|
| baseline | 3/3 | 609,404 | 149,061 | 248 | 0 | 0 |
| kernel_full (compression on) | 3/3 | **708,360** | 131,572 | 264 | **1** | 0 |
| kernel_no_compression | 3/3 | **420,201** | 106,417 | 243 | 0 | 0 |

The controlled contrast is **B vs C** (same extension, only compression differs):
B used **+69% tokens** (708k vs 420k) and +21 s wall for equal correctness, with
one repeat file read attributable to compression.

Raw: [`results-0005.json`](../data/results-0005.json).

## 5. Analysis

- **Correctness:** equal (3/3 all conditions).
- **H1 (support):** directionally supported. With compression **on**, the same
  extension used substantially **more** total tokens and slightly more wall time
  than with compression **off**, and produced the only repeat read. Compression
  shrank delivered per-call bytes (the vendor's target) yet raised end-to-end
  cost — the regression the Reddit discussion described.
- **A vs B:** the fully-enabled kernel also exceeded vanilla Pi on tokens
  (708k vs 609k), i.e. the efficiency claim did **not** hold on this long task
  for this model.
- **Caveat:** sums across only 3 cells; the comparison mixes cell composition, so
  this is a directional signal, not an effect estimate. It is exactly the pilot
  the design called for.

## 6. Threats to validity

- n=3, one task, one small model; the three cyclic trials are a position-balanced
  pilot, not the 6-trial estimate.
- A scored failure caused by the extension's own cache symlink was found and fixed
  in the scorer **before** this result; that was a false negative, not a result.
- Token totals are provider-reported; cost is undefined (no pricing), so
  efficiency is reported per million tokens / per hour, not USD.
- The instrumentation patch is a harness treatment, stated and hashed; it is not
  upstream.

## 7. Conclusion

- **H1 directionally supported; H0 not supported.** On a long, multi-file repair,
  compression reduced per-call output but increased total tokens and wall time at
  equal correctness.
- The vendor's short-term context saving and a long-horizon cost penalty can
  coexist. This does not refute the vendor's own benchmark; it shows the claim is
  **not uniform** and that "size per operation" is the wrong success metric.
- **Next:** run the 6-trial, two-task estimate and inspect per-call compression
  and repeated-retrieval episodes before any general claim.

## 8. Reproduction

```bash
docker/run.sh build
docker/run.sh tool vendor/pi-agent-kernel agent-kernel-instr   # after harness/instrument_kernel.py
export CONDITIONS_FILE="$PWD/experiments/kernel-retrieval.json" \
       CORPUS="$PWD/fixtures/widget-service" TASKS="$PWD/benchmarks" OUT="$PWD/out" \
       RUN_ID=kernel-retrieval TRIALS=3 TASK_LIST="repair_retrieval_long" \
       BASE_IMAGE=agent-codeintel-bench BENCH_IMAGE=agent-codeintel-bench-tool:agent-kernel-instr \
       TOOL_ENTRY=/opt/tools/agent-kernel-instr/src/index.ts \
       PI_PROVIDER=<p> PI_MODEL=<m> PI_THINKING=medium UPSTREAM_BASE_URL=<origin>
harness/run_isolated.sh
```

## 9. Data

- `docs/data/results-0005.json` — per-cell correctness, tokens, bytes, recovery,
  activation status.
