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

- **Design:** baseline vs enhanced; the *only* difference is the tool.
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

Raw, uninterpreted results. One table per task family: baseline vs enhanced,
score, tokens, wall time, tool calls, and — for the enhanced arm — the count of
tool-specific calls. Link the machine-readable data.

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

Accept or reject each hypothesis. State the adoption recommendation and the
smallest next step. A missing prerequisite is `blocked`, never `concluded`.

## 8. Reproduction

Exact commands and environment. Where data is withheld (private corpus), say so
and give the aggregate shape instead.

## 9. Data

Paths to raw streams, `metrics.json`, and the summarised CSV.
