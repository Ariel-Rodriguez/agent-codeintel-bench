# Report 0002 — Agent-kernel (AST/BM25 + embeddings + LSP)

- **Status:** concluded (navigation + impact; repair/persistence not run)
- **Tool under test:** `floydous/pi-agent-kernel` @ `b9e93be` (v0.4.0), default
  `lean` profile (AST-aware BM25; the ONNX embedding path was not exercised)
- **Model:** local `Qwen3.8-27B IQ3_S, 224k context`, thinking `medium`
- **Corpus:** the same private Python service as report 0001 (shape in Materials)
- **Isolation:** one fresh container per condition; **no direct network egress**
  (model via allowlisted gateway); references never mounted; scoring host-side
- **Claim:** issue
  [#1](https://github.com/Ariel-Rodriguez/agent-codeintel-bench/issues)

## 1. Hypothesis

- **H1:** agent-kernel improves **correctness** on navigation and impact.
- **H2:** it reduces **input-token cost** on those tasks.
- **H3:** its distinctive `code_search` tool is **used**.
- **Falsification:** H1 if scores are equal; H2 if the enhanced arm is not
  cheaper; H3 if `code_search` is never called.

## 2. Method

Same design as [report 0001](0001-structural-code-index.html), with two changes:

1. `harness/run_isolated.sh` runs **one fresh container per condition** and only
   mounts the corpus and the single task prompt (read-only); references stay on
   the host and scoring runs there. This removes the answer-leakage present in
   report 0001.
2. The enhanced arm is a **per-tool image** (`docker/run.sh tool`) with agent-kernel's
   npm dependencies vendored at build time, so the run is offline.

Before measuring: `harness/scan_extension.py` (static scan) and `docker/run.sh
probe` (no-network load of the exact entry). The probe reported
`PROBE LOAD OK {"tools":["read","edit","code_search"], ...}` — agent-kernel
**redefines** `read`/`edit` and adds `code_search`.

Arms: baseline `read,bash,edit,write`; enhanced the same plus agent-kernel.
3 counterbalanced trials per task, sequential. Model thinking `medium`.

## 3. Materials

- Harness: this repository; `pi 1.2.0`; Python 3.11 container.
- Tool: agent-kernel v0.4.0 at `b9e93be`, dependencies vendored into the image.
- Corpus shape (counts only): 105 files, 4 top-level directories, 21,843 code
  lines, 91 Python modules, 170 classes, 1,392 functions, 547 methods, 693
  imports, 135,063 AST nodes, max AST depth 17
  ([`corpus-reference-complexity.json`](../data/corpus-reference-complexity.json)).
- Isolation proof: the agent image contains **no** `benchmarks/`; the container is
  on an internal network with the model reachable only through the gateway; the
  probe ran with `network_mode: none`.

## 4. Evidence

Scores: navigation /7, impact /5. Three trials each; means ± population sd.

| family | arm | scores | input tok | output tok | tools | wall s |
|---|---|---|---|---|---|---|
| navigation | baseline | 7,7,7 | 6,009 ± 1,774 | 1,997 | 6.7 | 26.6 |
| navigation | enhanced | 7,7,7 | 3,561 ± 544 | 2,039 | 7.0 | 29.3 |
| impact | baseline | 5,5,5 | 5,968 ± 889 | 1,701 | 5.3 | 23.5 |
| impact | enhanced | 5,5,5 | 3,424 ± 1,239 | 1,270 | 4.7 | 21.1 |

Paired input-token differences (enhanced − baseline), per trial:

- navigation: −4,237 / −2,859 / −248 (mean **−2,448**, all negative)
- impact: −2,087 / −2,602 / −2,944 (mean **−2,544**, all negative)

**Tool use:** `code_search` was called **0 times** in all six enhanced runs. The
enhanced arm's calls were `read` (agent-kernel's redefined tool) and `bash`.

Raw, machine-readable: [`results-0002.json`](../data/results-0002.json).

## 5. Analysis

- **Correctness (H1):** equal at the ceiling under both arms; **not demonstrated**.
- **Cost (H2):** supported. Input tokens fell in **all 3 trials on both tasks**
  (mean −41% navigation, −43% impact), with no increase in tool calls and a small
  wall-time change.
- **Attribution (H3):** rejected. The saving did **not** come from agent-kernel's
  distinctive `code_search` tool (never called); it tracks the tool's **redefined
  `read`**, which returns more compact context. The headline capability was
  available and unused, so this is a *context-shaping* effect, not evidence that
  structural search helps.

## 6. Threats to validity

- Small n (3 trials per task); a single model (local IQ3_S).
- Correctness is at the ceiling, so H1 cannot distinguish the arms.
- `code_search` non-use means the treatment was only partially exercised.
- The ONNX embedding path (`hybrid`/`full` profiles) was not run, because the
  embedding model would need to be baked offline; results describe the `lean`
  profile.
- agent-kernel replaces built-in tools, so "added code intelligence" is a larger
  change than report 0001.
- Repair and persistence were not run (offline test deps and cross-session state);
  report scope is navigation + impact.

## 7. Conclusion

- **H1 not demonstrated**, **H2 supported**, **H3 rejected**.
- agent-kernel reduced context cost materially and reproducibly on this corpus,
  with no correctness change; but the effect came from its redefined `read`, not
  from structural code search, and its main tool went unused.
- **Recommendation:** worth a follow-up specifically on *why* `code_search` is
  not selected (prompting/steering), and a hybrid-profile run, before any
  adoption claim.

## 8. Reproduction

```bash
docker/run.sh build
docker/run.sh tool /path/to/pi-agent-kernel agent-kernel
source work/tool.env
python3 harness/scan_extension.py "$TOOL_PATH"
docker/run.sh probe

export CORPUS=<repo-or-zip> TASKS=<private-tasks-dir> RUN_ID=run1 TRIALS=3 \
       TASK_LIST="navigation impact" \
       BENCH_IMAGE="$TOOL_IMAGE" TOOL_ENTRY="$TOOL_ENTRY" \
       ENHANCED_TOOLS="read,bash,edit,write,code_search" \
       PI_PROVIDER=<p> PI_MODEL=<m> PI_THINKING=medium \
       UPSTREAM_BASE_URL=<model-origin>
harness/run_isolated.sh
```

## 9. Data

- `docs/data/results-0002.json` — 12 cells (score, tokens, tools, wall).
- `docs/data/corpus-reference-complexity.json` — corpus shape.
- Raw streams, prompts, and diffs are retained privately (they contain task
  content) and are not published; `harness/evaluate.py` scored them host-side,
  and `docs/reviews/astra-p1p2.md` records the provenance checklist.
