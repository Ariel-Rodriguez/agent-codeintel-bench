# Report 0004 — Agent-kernel on a cross-module discovery repair

- **Status:** concluded (exploratory; one task, n=3)
- **Tool under test:** `floydous/pi-agent-kernel` @ `b9e93be` (v0.4.0), `lean`
  profile, vendor guidance applied
- **Model:** local `Qwen3.8-27B IQ3_S, 224k context`, thinking `medium`
- **Corpus:** the same private Python service as reports 0001–0003
- **Isolation:** fresh container per condition; **no network egress**; hidden
  tests run host-side; repair scored by real tests

This follows report 0003, which showed a large, consistent efficiency gain on a
guard-restoration repair. This report asks whether that gain **reproduces on a
harder task that requires discovery**.

## 1. Hypothesis

- **H1:** agent-kernel improves **repair success** on a discovery task.
- **H2:** it reduces **cost** (input tokens, wall time) as it did in report 0003.
- **H3:** its `code_search` tool is **used** when the location is not given.

## 2. Method

Same design as [report 0003](0003-agent-kernel-repair.html). One **harder**
repair task:

- **Bug:** a fail-closed guard was removed from a readiness classifier, so an
  unattested fact could be treated as ready.
- **Prompt (symptom-described):** "the automator's protected credential flow can
  authorize a physical action when one of its readiness facts was never
  attested" — the module and function are **not** named, so the agent must locate
  the cause.
- **Hidden verification:** `components/automator/tests/test_credential_transaction.py`
  must pass (the fixture fails exactly one test); test changes are rejected.

3 counterbalanced trials; executable scoring as in report 0003.

## 3. Materials

As reports 0001–0003. `scan_extension.py`/probe unchanged; agent-kernel loads
offline and registers `read`, `edit`, `code_search`.

## 4. Evidence

| arm | repaired | input tokens | output tokens | tool calls | wall s |
|---|---|---|---|---|---|
| baseline | 3 / 3 | 18,481 ± 1,595 | 5,424 | 21.3 | 109 |
| enhanced | 3 / 3 | 20,316 ± 8,384 | 4,925 | 16.0 | 91 |

Paired input differences (enhanced − baseline): **−3,757 / −6,591 / +15,852**
(mean **+1,835**; one large outlier).

**Tool use:** `code_search` was called **0 times** in all six runs. Enhanced calls
were `read` (9), `edit` (3), `bash` (36); baseline `read` (9), `edit` (3),
`bash` (52).

Raw, machine-readable: [`results-0004.json`](../data/results-0004.json).

## 5. Analysis

- **H1 (correctness):** both arms repaired all three trials; **not demonstrated**.
- **H2 (cost):** **not supported consistently.** Two trials were cheaper
  (−3.8k, −6.6k input) and one was far more expensive (+15.9k input, 155 s vs
  54 s, 24 vs 14 tool calls). Mean input rose ~10%, dominated by that outlier.
  The enhanced arm did use **fewer tool calls on average** (16.0 vs 21.3) and
  less wall time on average (−16%), but the effect is not robust at n=3.
- **H3 (search used):** **rejected** — still zero `code_search` calls, even
  though this task required locating an unnamed cause. The tool's distinctive
  capability remains unexercised.
- **Bounding report 0003:** the −49% input / −46% wall result does **not**
  generalise as a constant. It reproduced on a narrow guard-restoration task but
  not on a cross-module discovery task; the gain is task-dependent and noisy.

## 6. Threats to validity

- One task, n=3, one model; a single outlier dominates the mean.
- Ceiling on success: both arms solved it, so H1 cannot separate them.
- `code_search` non-use means a search-quality claim is still untested.
- The two repair tasks differ in more than discoverability (bug shape, size),
  so the contrast is not a clean single-variable comparison.

## 7. Conclusion

- **H1 not demonstrated; H2 not supported consistently; H3 rejected.**
- The efficiency gain seen in report 0003 is **real but task-dependent**, not a
  uniform property of the tool. On a discovery repair it was within noise with
  one large outlier.
- The tool's headline capability (`code_search`) has now gone unused across
  navigation, impact, and two repair tasks. **Adoption of the search feature is
  not justified by any result so far**; the observed savings come from output
  shaping and reduced interaction.
- **Next:** run both repair tasks together for a 2-task estimate, and add a
  task that is solvable **only** by search (no identifiable failing test name the
  agent can just read) to force `code_search` use.

## 8. Reproduction

```bash
export CORPUS=<private-snapshot> TASKS=<private-tasks> RUN_ID=ru TRIALS=3 \
       TASK_LIST="repair_unattested" \
       BENCH_IMAGE="$TOOL_IMAGE" TOOL_ENTRY="$TOOL_ENTRY" \
       GUIDANCE_FILE=/opt/tools/agent-kernel/AGENT_KERNEL_SYS_PROMPT.md \
       ENHANCED_TOOLS="read,bash,edit,write,code_search" \
       PI_PROVIDER=<p> PI_MODEL=<m> PI_THINKING=medium UPSTREAM_BASE_URL=<origin>
harness/run_isolated.sh
```

## 9. Data

- `docs/data/results-0004.json` — 6 cells with tokens, tools, wall, per-tool
  counts.
