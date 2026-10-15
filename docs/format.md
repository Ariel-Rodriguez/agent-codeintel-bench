# Report format

Every experiment is written up with the sections below, in this order. The goal
is that a skeptical reader can decide, without trusting the author, whether the
conclusion follows from the evidence.

## Header

- **Report id and title**
- **Status:** `planned` | `in progress` | `concluded` | `blocked`
- **Tool under test:** name and pinned revision (results hold only for that revision)
- **Model(s):** provider/model and thinking level
- **Corpus:** aggregate shape only (see below)
- **Isolation:** how untrusted code was contained

## 1. Hypothesis

State the claim as testable hypotheses before running anything:

- **H1:** the tool improves `<quality metric>` on `<task family>`.
- **H0:** no improvement.
- Optionally secondary hypotheses (cost, latency).

State in advance what would falsify H1.

## 2. Method

- **Design:** declare scientific (vanilla vs vanilla + candidate) and adoption
  (frozen configured Pi vs configured Pi + candidate) pairs independently. Within
  each pair the *only* difference is the candidate. Existing A/B/C ablations stay
  separate contrasts. See [Dual-baseline workflow](dual-baseline.md).
- **Personal baseline:** sanitized snapshot SHA-256, exact Pi/model/thinking,
  ordered pinned extensions, tools, settings/env and configuration hashes;
  document differences from vanilla. An unreproduced actual setup blocks adoption.
- **Tasks:** the task families and what each requires.
- **Ordering:** counterbalanced, sequential; number of trials per cell.
- **Controls:** fixed prompt, fixed corpus commit, fixed model and thinking,
  fixed built-in tool budget.
- **Isolation:** container, no direct network egress, allowlisted model gateway;
  static scan and no-network probe of the tool.
- **Metrics:** quality score (definition in `reference.json`), input/output
  tokens, wall time, tool calls, and a forced error on any failed prerequisite.
- **Analysis plan:** paired deltas per task; report variance; do not pool tasks
  with different scoring maxima without normalising.

## 3. Materials

- Harness and tool revisions (commit ids).
- Runtime versions (agent, Node, Python).
- Corpus shape:

  | metric | value |
  |---|---|
  | files | |
  | top-level directories | |
  | code / comment / blank lines | |
  | languages (by code lines) | |
  | modules, classes, functions, methods | |
  | import statements | |
  | AST nodes, max AST depth | |

  Counts only. No identifiers, paths, or semantics.

## 4. Evidence

Raw, uninterpreted results. One table per task family and declared comparison:
score and scoring method (rubric vs executable tests), input/output/total tokens,
wall time, tool calls/use, and repeated retrieval where instrumentation supports
it. Include every planned trial, missing/invalid cells, activation proof and
captured resources for unsuccessful attempts. Link `comparisons.json` and raw
machine-readable evidence. Unavailable metrics are not zero; no USD is inferred
for unpriced/local models.

## 5. Analysis

Paired differences, means and spread, and an explicit statement of what can and
cannot be attributed to the tool. Distinguish:

- **Demonstrated:** repeated across counterbalanced trials.
- **Suggested:** consistent but small n.
- **Not demonstrated:** within noise, or contradicted.

## 6. Threats to validity

Small n, provider nondeterminism, keyword scoring, contamination, missing
isolation boundaries, a patched tool being a different treatment, and anything
else that could explain the result without the hypothesis being false.

## 7. Conclusion

Accept or reject each hypothesis and provide **two independent verdicts**:

- **Scientific:** does the candidate reproducibly benefit vanilla Pi?
- **Adoption:** does it improve our actual frozen configured Pi enough to enable?

Use **Adopt / Adopt selectively / Experimental / Reject / Insufficient evidence /
Blocked or invalid experiment**. Automated positive screens remain Experimental;
justify promotion with repeated practical benefits on relevant workloads, no
observed correctness regression, and compatibility review. Mixed results remain
workload-dependent. Equal ceiling scores do not establish correctness equivalence
on harder tasks. Specify the smallest next step. Missing personal configuration
may block adoption while leaving scientific evidence interpretable. Missing
prerequisites never become measured success. Actual enabling requires a separate
explicit owner decision; a report never modifies the daily-use environment.

## 8. Reproduction

Exact commands and environment. Where data is withheld (private corpus), say so
and give the aggregate shape instead.

## 9. Data

Paths to raw streams, `metrics.json`, and the summarised CSV.

## 10. Provenance checklist

A report is not reviewable unless every item below is recorded (publish only the
non-sensitive ones; keep private ones referenced by hash):

- Tool: name, **exact revision** (commit sha or version), and any local patch.
- Model: provider, model id, thinking level, and any revision/digest served.
- Corpus: snapshot hash and aggregate shape (see section 3), plus the exclusion
  rules (no credentials, no `.git`, no hooks, no environments, no answers).
- Prompts: sha256 of each prompt actually sent.
- References: sha256 of each `reference.json`; they stay host-side.
- Images: digest of the baseline and per-tool images; lockfiles used. Explicit
  dual-baseline pairs use the same preprovisioned image with candidate loading as
  the treatment, not a second image change.
- Plan: immutable expected trials/tasks, manifest identity, paired condition
  inheritance, baseline snapshot hashes and task/verification asset hashes.
- Isolation: proof that the agent container had no reference/answer mount, and
  network assertions (internal network, gateway allowlist, no external DNS/TCP).
- Tool activation: per run, evidence the tool was **registered and called** (or
  its relevant hook/wrapper actually executed), with correct implementation,
  revision, effective settings and no unexpected wrapper conflicts. Registration
  alone is not execution. Report non-use/invalid runs instead of dropping them.
- Failures: any cell that failed closed, with its exit code and stream status.
- Adjudication: how each score was decided, including any manual override.

Do not treat a README claim, a plan, or a model's own answer as a measured
result. Unmeasured metrics are marked unavailable.
