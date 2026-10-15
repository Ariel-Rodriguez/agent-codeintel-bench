# Agent Code-Intelligence Benchmark

Does adding structural code intelligence to a coding agent improve what it
produces? This site reports controlled A/B experiments — one tool at a time —
in a fixed, reviewable format.

## Reports

| # | Tool | Status | Headline |
|---|---|---|---|
| [0001](reports/0001-structural-code-index.html) | structural code-index extension | concluded | No correctness benefit; token effect depends on the model |
| [0002](reports/0002-agent-kernel.html) | agent-kernel (AST/BM25 + embeddings + LSP) | concluded | Navigation/impact: input −41/−43%, but `code_search` unused |
| [0003](reports/0003-agent-kernel-repair.html) | agent-kernel on a repair task | concluded | **Repair: input −49%, wall −46% at equal success** — vendor claim direction transfers |
| [0004](reports/0004-agent-kernel-discovery-repair.html) | agent-kernel on a discovery repair | concluded | Gain **did not reproduce** (2 cheaper, 1 big outlier); `code_search` still 0 |
| [0005](reports/0005-long-horizon-retrieval-regression.html) | Long-horizon retrieval regression (A/B/C) | concluded (pilot) | Compression **on** used **+69% tokens** than compression **off**, equal correctness |
| [Review](reviews/astra-p1p2.html) | astra — repository P1/P2 and next-experiment plan | open | Fixes in progress |

## The format

Every report uses the same sections so results can be compared across tools:
**Hypothesis → Method → Materials → Evidence → Analysis → Threats → Conclusion →
Reproduction**. The template is in [Report format](format.html).

## How to read a result here

- Correctness and cost are reported separately. A tool can save tokens and still
  not be worth adopting, or vice versa.
- Every number comes from a stored run: prompt hash, event stream, exit code,
  wall time, token usage, and tool calls. See the repository's `harness/`.
- Sample sizes are small. A single trial is labelled as such; effects are only
  claimed when they repeat across counterbalanced trials.
- "The tool is installed" is never treated as evidence that it was used; each
  report verifies tool visibility and execution in the raw stream.

## Corpora

Reports state the corpus **shape** (files, lines, symbol and AST-node counts) so
readers can judge how hard the task was — without disclosing any source,
identifiers, or semantics of a private repository.

## Repository

Harness and methodology: [github.com/Ariel-Rodriguez/agent-codeintel-bench](https://github.com/Ariel-Rodriguez/agent-codeintel-bench).
