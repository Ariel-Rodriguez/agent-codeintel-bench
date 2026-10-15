# Run — pi-agent-kernel 6×2 (A/B/C)

- **Status:** concluded (6 trials, 2 tasks; all 36 cells valid, none blocked)
- **Tool under test:** `floydous/pi-agent-kernel` @ `b9e93be` (v0.4.0, `lean`)
  plus the harness instrumentation patch (`KERNEL_NO_COMPRESSION` bypass + wrapper
  audit)
- **Model:** local `Qwen3.8-27B IQ3_S, 224k`, thinking `medium`
- **Corpus/tasks:** public `widget-service` fixture, `repair_retrieval_long` and
  `repair_retrieval_small`
- **Isolation:** fresh container per cell, sequential, no network egress,
  host-side executable scoring; treatment activation verified from the audit
  sidecar in every kernel cell

## 1. Hypothesis

- **H1:** output compression reduces per-call output but can **increase
  long-horizon total cost**.
- **H0:** compression lowers cost without a long-horizon penalty.
- Correctness is reported separately so a cheaper failure cannot look better.

## 2. Method

| condition | extension | compression |
|---|---|---|
| `baseline` | none | native Pi |
| `kernel_full` | kernel + instrumentation | **on** |
| `kernel_no_compression` | same | **off** (`KERNEL_NO_COMPRESSION=1`) |

6 counterbalanced trials (all six orderings), sequential, one fresh container per
cell, cell-only output mount, trusted host-side tests, wrapper-activation proof.

## 3. Materials

Tool revision `b9e93be`; instrumentation patch adds the C bypass and the audit and
is present but inactive in B. Every kernel cell reports
`activation_status: verified`. Public fixture + the two retrieval-repair tasks.

## 4. Evidence

Pooled (12 cells per condition):

| condition | correct | total tokens | tool-response bytes | wall s | repeat reads | post-truncation |
|---|---|---|---|---|---|---|
| baseline | 12/12 | 2,329,140 | 499,394 | 967 | 1 | 0 |
| kernel_full (compression on) | 12/12 | 2,215,194 | 462,991 | 992 | 2 | 0 |
| kernel_no_compression | **11/12** | 1,808,945 | 417,520 | 865 | 3 | 0 |

Per task:

| task | condition | correct | total tokens | wall s |
|---|---|---|---|---|
| long | baseline | 6/6 | 1,061,172 | 436 |
| long | kernel_full | 6/6 | 1,147,473 | 490 |
| long | kernel_no_compression | 6/6 | 764,412 | 392 |
| small | baseline | 6/6 | 1,267,968 | 532 |
| small | kernel_full | 6/6 | 1,067,721 | 503 |
| small | kernel_no_compression | 5/6 | 1,044,533 | 473 |

Raw: [`kernel-6x2.json`](kernel-6x2.json).

## 5. Analysis

- **Correctness:** baseline and `kernel_full` are equal (12/12). Disabling
  compression cost one failure (11/12). Equal success is not proof of equal
  correctness on harder tasks, but here there is no observed advantage.
- **Long task (all 6/6 correct), the clean contrast:** compression **on** used
  **+50% tokens** vs **off** (1,147,473 vs 764,412), and also exceeded vanilla
  (1,061,172). This reproduces the pilot directionally at n=6: compression shrank
  delivered bytes yet raised end-to-end cost.
- **Small task:** the kernel (both modes) used **fewer** tokens than vanilla
  (~1.05–1.07M vs 1.27M). So the effect is **workload-dependent**: it helps on
  short tasks and hurts on the long one when compression is on.
- **Mechanism:** repeated reads do **not** explain it (baseline 1, full 2,
  off 3), and post-truncation retrieval episodes were **0** everywhere. The extra
  cost is therefore not primarily re-reads; it is more consistent with extra turns
  or larger accumulated context — consistent with the pilot and with the earlier
  note.

## 6. Threats to validity

- One model (small local), two tasks, n=6 per task. Exploratory, not universal.
- The single failure in `kernel_no_compression` (small task) confounds the pooled
  cost comparison; the **long task with all cells correct** is the reliable
  contrast.
- Tokens are provider-reported; no USD (local model), efficiency is per-million
  tokens / per hour.
- The instrumentation patch is a harness treatment, stated and hashed; it is not
  upstream.

## 7. Verdicts

- **Scientific (kernel vs vanilla):** **Adopt selectively / Experimental.**
  No correctness benefit; a real cost benefit on the short task; a real
  long-horizon cost penalty when compression is on. Not a general improvement.
- **Compression:** enabling it raises long-horizon cost here; disabling it is
  cheaper on the long task but cost one correctness failure on the small task, so
  it is not a free win either.
- **Adoption:** **Blocked** — no sanitized personal baseline was supplied, so the
  adoption comparison was not run. Do not infer adoption from this scientific run.

## 8. Reproduction

```bash
export CONDITIONS_FILE="$PWD/experiments/kernel-retrieval.json" \
       CORPUS="$PWD/fixtures/widget-service" TASKS="$PWD/benchmarks" OUT="$PWD/out" \
       RUN_ID=kernel-6x2 TRIALS=6 TASK_LIST="repair_retrieval_long repair_retrieval_small" \
       BASE_IMAGE=agent-codeintel-bench BENCH_IMAGE=agent-codeintel-bench-tool:agent-kernel-instr \
       TOOL_ENTRY=/opt/tools/agent-kernel-instr/src/index.ts \
       PI_PROVIDER=<p> PI_MODEL=<m> PI_THINKING=medium UPSTREAM_BASE_URL=<origin>
harness/run_isolated.sh
```

## 9. Data

- [`kernel-6x2.json`](kernel-6x2.json) — 36 cells with correctness, tokens,
  bytes, wall, recovery counts, activation status.
