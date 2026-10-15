# Diagnosis — astra (openai/gpt-6-astra, medium)

- Date: 2026-10-15
- Question: why (near) no outcome vs the vendor's claimed gains; should we host ONNX; next experiment.
- Read-only. Review, not a report.

---

## Bottom line

You did **not** observe “near no outcome.” You observed **41–43% lower reported input tokens at unchanged ceiling scores**, without using `code_search`. The vendor likewise reports **no correctness improvement**: both Pi arms solved **8/8**. Its headline is efficiency, not improved correctness.

Your experiment tests a narrower, different claim: **default-lean extension loading on two short Python information-retrieval tasks with quantized local Qwen**. It does not reproduce the vendor’s **installed product on eight bug fixes with `cx/gpt-5.6-luna:high`**.

There are also actual methodological problems in the repository—not just differences of scope.

I inspected the repository read-only. Vendor-specific statements below rely on the excerpts you supplied; I did not independently inspect its benchmark implementation.

## 1. What is wrong—and what is merely different?

### A. Your interpretation understates the efficiency result

| Metric | Vendor: kernel vs vanilla | Your navigation | Your impact |
|---|---:|---:|---:|
| Correctness | 8/8 vs 8/8 | 7/7 vs 7/7 | 5/5 vs 5/5 |
| Input tokens | **−61.9%** | **−40.7%** | **−42.6%** |
| Output tokens | **−58.2%** | **+2.1%** | **−25.3%** |
| Tool calls | **−28.2%** | **+4.5%** | **−11.3%** |
| Wall time | **−51.0%** | **+10.2%** | **−10.2%** |
| “Total turn tokens” | **−44.1%** | Not established on equivalent accounting | Same |

Your input savings are directionally consistent with the vendor’s claim. What does **not** transfer so far is its large latency reduction and consistent reduction in interaction volume.

That distinction matters: fewer input tokens need not mean proportionally faster execution. Navigation output barely changed, tool calls increased slightly, and fixed startup/tool overhead can dominate a **~27-second** run. Long repair sessions offer more opportunities to avoid repeated context and generation.

### B. These tasks cannot test correctness improvement effectively

Both tasks already saturate their rubrics. They require neither producing a patch nor successfully running tests. Consequently:

- Edit verification is untested.
- Repair/test iteration savings are untested.
- Long-session context management is barely tested.
- Semantic discovery may offer little advantage over searching a supplied symbol.
- Three repetitions of two tasks are **not six independent task samples**.

The corpus has **105 files and 21,843 code lines**, but corpus size does not establish task difficulty. Locating a named function and its consumers can remain easy in a much larger repository.

**Classification:** valid narrow efficiency benchmark; inappropriate basis for rejecting a bug-fixing claim.

### C. Your rubric is weaker than “correctness” implies

[`harness/evaluate.py`](harness/evaluate.py) scores **substring inclusion/exclusion in final prose**. It does not independently establish that a consumer list is exhaustive, a proposed rename is safe, or a repair works.

That can create a scoring ceiling even where substantive answer quality differs. Without the private references and answers, I cannot determine whether it did here.

For impact tasks, score explicit entity sets with precision/recall and false-positive penalties. For repair tasks, score the resulting artifact with regression tests.

**Classification:** actual measurement limitation.

### D. The input-token metric is already cumulative—not merely one response

In [`harness/evaluate.py`](harness/evaluate.py), `parse_run()` sums `usage.input` over **every assistant `message_end`**. Therefore the reported input metric is cumulative across the run’s model responses, assuming the provider supplies correct usage. It is not just the final response’s input or an average per response.

But it may still differ from the vendor’s accounting:

- `cacheRead` and `cacheWrite` are collected separately.
- `totalTokens` is summed separately.
- Providers differ in whether their input counters include cached tokens.
- Reasoning may already be included in output; blindly adding it can double-count.
- Missing usage currently becomes zero, which can silently undercount.

The vendor’s numbers themselves require clarification:

- Kernel: **270k input + 13.5k output = 283.5k**, not **861k**.
- Vanilla: **709k + 32.3k = 741.3k**, not **1.54M**.

Those gaps could reflect cached input or a different definition, but the excerpt does not establish which.

**Required:** obtain the vendor’s aggregation code or raw usage, then report separately:

1. Cumulative logical input, including cached context exactly once.
2. Cumulative output and reasoning accounting.
3. Uncached/cache-read/cache-write usage.
4. Actual billed cost, where meaningful.

Do **not** equate “input tokens,” “total turn tokens,” and cost.

### E. The attribution to redefined `read` is contradicted by your own data

Report 0002 says the savings came from redefined `read`. That is too strong.

In [`docs/data/results-0002.json`](docs/data/results-0002.json):

- Impact trial 1: **both arms used only `bash`**, yet input fell **7,172 → 5,085**.
- Impact trial 3: **both arms used only `bash`**, yet input fell **5,054 → 2,110**; calls fell **9 → 3**.

Those savings cannot be attributed to executed `read` calls.

Possible causes include bash-output hooks, different commands, fewer turns, extension instructions, or tool-schema effects. The load probe reports registrations for **read/edit/code_search**, not proof that `bash` itself was redefined. A hook could still alter bash behavior.

**Defensible conclusion:** savings occurred without explicit `code_search` calls. The specific mechanism remains unisolated.

### F. You changed the installed product’s treatment

Loading an entry with:

```text
-e <entry> --no-context-files --no-skills --no-prompt-templates
```

is not automatically equivalent to the advertised installation that adds `AGENT_KERNEL_SYS_PROMPT.md`.

If that guidance was absent, you tested **extension availability without its intended steering**. However, do not assume absence solely from flags: inspect the effective prompt and extension hooks.

For a product-level comparison, vendor instructions belong in the enhanced treatment—and their tokens count. For mechanism attribution, add a separate no-steering ablation.

**Classification:** treatment mismatch for reproduction; legitimate variant for a deliberately minimal-loading benchmark.

### G. Model and profile are effect modifiers, not excuses

Your **Qwen IQ3_S, medium thinking** differs materially from **`cx/gpt-5.6-luna:high`** in tool selection, generation speed, reasoning behavior, and possibly usage accounting. No evidence here identifies which difference matters.

Likewise, `lean` is a valid default-product test. The vendor excerpt does not establish that its benchmark used hybrid/full. Do not assume embeddings explain its gains.

Zero search calls means changing the search backend alone has no demonstrated route to improve retrieval. Background initialization or prompt changes could still affect overhead or behavior.

**Classification:** transfer limits, not evidence that your model or profile is “wrong.”

### H. The claimed cross-run isolation is not actually enforced

[`harness/run_isolated.sh`](harness/run_isolated.sh) mounts:

```bash
-v "$OUT:/out"
```

That exposes the **entire results root** to every condition. Prior transcripts, prompts, and patches are therefore accessible. After host-side scoring, `metrics.json` also contains rubric check names.

This contradicts the script’s claim that other runs are never mounted. Fresh containers do not fix shared-volume visibility.

There is **no evidence here that agents exploited it**, but the exposure exists. Mount only the current cell’s output directory. Keep scored artifacts outside anything future agents can access.

**Classification:** actual isolation defect.

## 2. Is the vendor benchmark comparable?

**Only qualitatively at present.** Both ask whether the package can maintain task success while reducing resource consumption. They do not estimate the same workload/model/configuration effect.

A fair reproduction of **their** claim requires:

- The exact eight issues, buggy commits, prompts, and acceptance tests—not merely the same repository names.
- The vendor’s actual Agent-Kernel revision, profile, configuration, and installed system guidance.
- Its exact Pi version and model endpoint/version, with `high` reasoning and matching budgets.
- Matching dependency availability, test commands, timeout policy, and retry policy.
- Defined cold/warm index and model-cache conditions.
- Identical token-accounting definitions.
- Multiple counterbalanced repetitions, with all failures and timeouts retained.

Your network isolation is compatible with that if dependencies and models are provisioned beforehand. If the vendor relied on live downloads or browsing, disclose the difference.

Comparisons against Codex CLI, OpenCode, and Claude Code do **not** isolate Agent-Kernel’s contribution: they bundle harness defaults, prompts, tool behavior, and accounting differences. The relevant controlled comparison is **Pi vanilla versus Pi + Kernel**.

Until the vendor supplies task artifacts and accounting, its exact efficiency claim is **not independently reproducible from this excerpt**. That is not proof it is false.

## 3. Should you host embeddings on `popos`?

**Not as the next experiment.**

First distinguish two proposals:

- **Pre-cache ONNX assets and execute locally in the agent container:** appropriate for an offline hybrid/full test.
- **Serve embeddings over HTTP from `popos`:** only appropriate if the extension explicitly supports that backend. An ONNX-in-process implementation does not automatically support a remote embedding service.

A remote service also introduces another network exception, latency component, and possible shared cache.

Before adding embeddings:

1. Verify `code_search` actually executes offline and returns relevant results—not just that it registers.
2. Restore the intended system guidance.
3. Verify its description and schema reach the model.
4. Use at least one behavior-described task without a supplied symbol or filepath.
5. Record query arguments, returned results, errors, and whether subsequent edits use those results.

A forced-search diagnostic can test **retrieval quality conditional on use**. It cannot establish natural adoption or justify deleting zero-use runs from the product benchmark.

Only after search is used should you compare **lean versus hybrid**, holding steering and tasks constant. Otherwise you are provisioning a backend for an unselected tool.

## 4. Minimal next experiment

### Design: a bounded transfer test, not another navigation benchmark

Use **two preselected real repair tasks** on the private Python corpus:

1. **Semantic localization:** a reproducible behavioral failure spanning at least two modules; prompt contains the symptom and reproduction, but no implementation symbol/path.
2. **Regression repair:** an API behavior bug requiring implementation and caller/test changes, with enough test output and iteration to exercise output shaping and edit verification.

Prepare all dependencies offline. Hidden tests remain host-side. Verify that they fail on the starting snapshot and pass on a known valid repair.

Run **three counterbalanced repetitions per task**, with:

- **A:** vanilla Pi.
- **B:** complete vendor lean treatment, including verified vendor guidance.

That is **12 runs**. Keep the current Qwen model to answer transfer to your deployment. If the objective instead is direct reproduction, substitute the vendor’s exact model and tasks; do not call a Qwen/private-Python result a replication.

Do not require search in scored prompts. Beforeward, run a separate unscored smoke test explicitly requesting one search to establish functionality.

### Metrics

Primary:

- Hidden regression-test pass rate and pre-existing test failures.
- Cumulative logical input and output under validated accounting.
- End-to-end agent wall time.

Secondary:

- Provider-reported uncached and cached tokens.
- Model-response count; calls by tool.
- Search calls/errors, result size, symbol-read use.
- Tool-output bytes, test invocations, edit failures.
- Index/startup time, separately and included in total.
- Timeouts and failed runs—never silently excluded.

Show paired results for each task/trial. With only two tasks, report an exploratory transfer result, not a general effect estimate.

### Commands and prerequisites

**Do not run the existing harness unchanged for this repair experiment.** It first needs these specific capabilities:

- Per-cell output mounts.
- Verified enhanced-only vendor system guidance.
- Complete final workspace capture: `git diff` currently omits untracked new-file contents.
- Host-side executable-test scoring; the existing scorer only checks prose.
- A precreated combined-results directory: the aggregator writes into `OUT/RUN_ID` without creating it.

After those prerequisites, the existing orchestration interface is:

```bash
# Proposed future execution; not executed in this diagnosis.
docker/run.sh build
docker/run.sh tool /absolute/path/to/pinned/pi-agent-kernel agent-kernel
source work/tool.env
python3 harness/scan_extension.py "$TOOL_PATH"
docker/run.sh probe

export CORPUS=/absolute/path/to/private-python-snapshot
export TASKS=/absolute/path/to/repair-tasks
export TASK_LIST="repair_semantic repair_regression"
export RUN_ID=kernel-lean-repair-qwen
export TRIALS=3
export OUT="$PWD/out"

export BASE_IMAGE=agent-codeintel-bench
export BENCH_IMAGE="$TOOL_IMAGE"
export TOOL_ENTRY
export ENHANCED_TOOLS="read,bash,edit,write,code_search"
export PI_PROVIDER='<existing-local-provider>'
export PI_MODEL='<exact-current-Qwen-model-id>'
export PI_THINKING=medium
export UPSTREAM_BASE_URL='<allowlisted-model-origin>'

mkdir -p "$OUT/$RUN_ID"
harness/run_isolated.sh
```

There is currently **no verified environment switch in this runner** that restores the vendor prompt or turns substring scoring into repair evaluation. Inventing one would give you a misleadingly runnable recipe.

### Decision rules

- **Same repair success, large token/time reduction:** efficiency gain transfers on these tasks.
- **Token savings but no latency improvement:** context-cost benefit transfers; speed claim does not.
- **No savings with complete treatment:** no demonstrated transfer to this model/workload; vendor result remains unrefuted.
- **Search remains unused despite verified availability and guidance:** adoption failure is itself the deployment result. Embeddings are not the next remedy.
- **Search is used but results are inadequate:** then test hybrid against lean.
- **Savings accompany more incorrect patches:** not an equivalent-quality efficiency gain.

The immediate priorities are **correct accounting, complete treatment, repair tasks, and fixing output isolation**—not hosting an embedding model.
