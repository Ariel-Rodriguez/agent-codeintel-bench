# Agent Code-Intelligence Benchmark

Evaluate Pi coding-agent extensions, tools, and optimizations **before** adopting
them. Trust measurements, not marketing claims.

The framework answers two separate questions with two separate baselines:

| Comparison | Baseline | Candidate | Answers |
|---|---|---|---|
| **Scientific** | vanilla Pi | vanilla Pi + candidate | Does the candidate help at all? |
| **Adoption** | our configured Pi | our configured Pi + candidate | Does it help *our* setup? |

A scientific win does **not** imply an adoption recommendation. Adoption requires
no correctness regression plus a repeatable, meaningful benefit.

## Runs

- [pi-agent-kernel 6×2 (A/B/C)](runs/kernel-6x2.md) — concluded: no correctness
  benefit; compression **on** cost **+50%** vs **off** on the long task at equal
  success; kernel helped on the short task. Adoption comparison **blocked**
  (no personal baseline).

## Start here

- [Dual-baseline workflow](dual-baseline.md) — conditions, comparisons, verdicts.
- [Report format](format.md) — the required structure for every result.
- [Agent workflow](../PROMPT.md) — how a coding agent runs a candidate end to end.
- [Adding a tool](../harness/adapters.md) — adapters and instrumentation.
- [Contributing](../CONTRIBUTING.md) — commit policy and how to claim a test.

## How it works

- A **manifest** (`experiments/*.json`) declares named conditions and the
  comparisons between them.
- The isolated runner executes each condition in a fresh container with no
  network egress, counterbalanced, sequentially.
- Correctness is verified by **executable tests** host-side; treatment activation
  is **verified from instrumentation**, never assumed.
- A comparison layer reports per-task paired correctness and resources and emits
  independent **scientific** and **adoption** verdicts.

## Statuses

`Adopt` · `Adopt selectively` · `Experimental` · `Reject` · `Insufficient evidence`
· `Blocked / invalid experiment`. Missing configuration or unverified activation
fails closed.

## Archive

Earlier single-candidate reports (0001–0005) and the legacy local runner are kept
under [`archive/`](../archive/) for provenance. They are superseded by the
dual-baseline framework and are not part of the current workflow.
