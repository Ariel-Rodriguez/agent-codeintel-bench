# Report 0003 — Agent-kernel on a repair task

- **Status:** concluded (exploratory; one repair task)
- **Tool under test:** `floydous/pi-agent-kernel` @ `b9e93be` (v0.4.0), `lean`
  profile, vendor guidance applied to the enhanced arm (`GUIDANCE_FILE`)
- **Model:** local `Qwen3.8-27B IQ3_S, 224k context`, thinking `medium`
- **Corpus:** the same private Python service as reports 0001/0002
- **Isolation:** fresh container per condition; **no network egress**; references
  and hidden verification host-side
- **Claim:** issue
  [#1](https://github.com/Ariel-Rodriguez/agent-codeintel-bench/issues)

This report exists because reports 0001/0002 used information-retrieval tasks,
which do not exercise what the tool claims to save. The vendor's own benchmark is
**bug repair**. This is a first repair test.

## 1. Hypothesis

- **H1:** agent-kernel improves **repair success**.
- **H2:** it reduces **cost** (input tokens, wall time) on a repair task.
- **H3:** its `code_search` tool is **used**.

## 2. Method

- **Task:** a real regression in the corpus (a freshness guard removed by a
  prepared fixture). The prompt describes the **symptom** ("a malformed
  observation is authorized; a test in the suite fails") without
  naming the function or the fix.
- **Arms:** baseline `read,bash,edit,write`; enhanced the same plus agent-kernel
  (with the vendor's own guidance). 3 counterbalanced trials.
- **Scoring is executable, not prose.** `harness/score_repair.py` reconstructs the
  agent's final workspace (corpus + fixture + `final.patch` + untracked files),
  **rejects any change to tests**, builds an offline venv, and runs the test
  suite in the container (`network=none`). Pass = exit 0. This replaces the
  substring rubric flagged in earlier reports.
- **Evidence of use:** tool calls counted from `tool_execution_start`.

## 3. Materials

- Harness: this repository; `pi 1.2.0`; pytest baked into the image; workspace
  venv created offline (`--system-site-packages`).
- Tool: agent-kernel v0.4.0 (`b9e93be`), dependencies vendored into the image.
- Corpus shape: as reports 0001/0002 (105 files, 21,843 code lines, 91 modules).
- `scan_extension.py` flagged agent-kernel for `child_process` (LSP installers),
  filesystem writes, and network use; the no-network probe confirmed it **loads
  and registers** offline (`read`, `edit`, `code_search`).

## 4. Evidence

Three trials; repair scored 0/1 (fail) or 1/1 (pass) by the real test suite.

| arm | repaired | input tokens | output tokens | tool calls | wall s |
|---|---|---|---|---|---|
| baseline | 3 / 3 | 15,492 ± 2,219 | 5,779 | 16.3 | 89.9 |
| enhanced | 3 / 3 | **7,940 ± 1,938 (−48.8%)** | **3,080 (−46.7%)** | 12.3 | **48.2 (−46.4%)** |

Paired input differences (enhanced − baseline): **−6,837 / −7,371 / −8,447**
(mean −7,552; all negative).

**Tool use:** `code_search` was called **once** across the three enhanced runs.
The rest of the enhanced calls were `read`, `edit`, `bash`.

Raw, machine-readable: [`results-0003.json`](../data/results-0003.json).

## 5. Analysis

- **H1 (correctness):** both arms repaired all three trials; **not demonstrated**
  (equal, at success).
- **H2 (cost):** **supported and large.** Input −49%, output −47%, wall −46%,
  with fewer tool calls, across three paired trials. This is the first experiment
  where the enhanced arm's cost is unambiguously and reproducibly lower.
- **H3 (search used):** effectively **rejected** (1 call). As in report 0002, the
  gain is **not** attributable to `code_search`; it tracks the tool's
  output-clamping, capped/compact reads, and reduced interaction, not structural
  search.
- **Relation to the vendor claim:** the vendor reports `−62% input` and `−51%`
  wall on eight bug fixes with a frontier model. On one repair task with a small
  local model we see **−49% input and −46% wall** — the same direction and
  similar magnitude. The claim **transfers**, whereas the navigation/impact
  tasks in report 0002 did not exercise it.

## 6. Threats to validity

- **One repair task**, n=3, one model. This is an exploratory transfer result,
  not a general effect estimate.
- The task is small (a guard restoration); it may not represent larger repairs.
- `code_search` non-use means a search-quality claim is still untested.
- The vendor's exact tasks/model/accounting differ; this is a transfer test, not
  a replication of their number.

## 7. Conclusion

- **H1 not demonstrated; H2 supported; H3 rejected.**
- On a repair task, agent-kernel's **efficiency claim transfers**: roughly half
  the tokens and wall time at equal success, consistent with the vendor's
  reported direction.
- The saving is **not** from its structural-search tool, which went essentially
  unused; it comes from output shaping and reduced interaction.
- **Next:** add a second, harder repair task (semantic localization across
  modules), then compare `lean` vs `hybrid` **only if** search is actually shown
  to be used offline.

## 8. Reproduction

```bash
docker/run.sh build
docker/run.sh tool /path/to/pi-agent-kernel agent-kernel
source work/tool.env

export CORPUS=<private-snapshot> TASKS=<private-tasks> RUN_ID=rk TRIALS=3 \
       TASK_LIST="repair_freshness" \
       BENCH_IMAGE="$TOOL_IMAGE" TOOL_ENTRY="$TOOL_ENTRY" \
       GUIDANCE_FILE=/opt/tools/agent-kernel/AGENT_KERNEL_SYS_PROMPT.md \
       ENHANCED_TOOLS="read,bash,edit,write,code_search" \
       PI_PROVIDER=<p> PI_MODEL=<m> PI_THINKING=medium \
       UPSTREAM_BASE_URL=<model-origin>
harness/run_isolated.sh
```

## 9. Data

- `docs/data/results-0003.json` — 6 cells with tokens, tools, wall, and per-tool
  call counts.
- Repair verification (`repair_result.json`) is produced by
  `harness/score_repair.py` and kept privately (it contains test output).
