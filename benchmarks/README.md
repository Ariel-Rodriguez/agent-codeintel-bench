# Benchmarks

Task families use host-side scoring: `reference.json` for retrieval answers,
`verify.json` plus trusted hidden tests for the new executable repair pair. All prompts target `fixtures/widget-service` and contain
no identifiers from any private corpus.

| id | family | what it measures |
|---|---|---|
| `navigation` | Symbol + consumer lookup | Does the tool reduce exploration cost/errors when locating a symbol and its callers/exports/tests? |
| `impact` | Rename impact analysis | Does the tool identify the exact definition/export/test files affected and correctly prove nothing outside the package changes? |
| `repair` | Bug repair | Does the tool help find the root cause of a failing test and apply the minimal correct fix? |
| `persistence` | Cross-session reuse | Does on-disk tool state (e.g. an index) answer follow-up questions in a **new** session better than a fresh agent? |
| `repair_retrieval_long` | Multi-module repair | Repeated retrieval and diagnostic recovery in a verbose integration flow (draft; compression pilots blocked) |
| `repair_retrieval_small` | Localized repair | Short-output startup/guidance overhead control (draft) |

Prompts are deliberately answer-neutral: they ask for evidence and for explicit
"unknown" when a fact cannot be verified.

`repair/bug.patch` is applied identically to both arms before the repair task, so
the two arms start from the same failing commit.

The retrieval repair pair is staged host-side from `fixture.patch`. References,
hidden tests and diagnostic definitions never enter agent images/mounts. See
[`repair_retrieval_long/README.md`](repair_retrieval_long/README.md) for offline
validation and the explicit source/probe/pilot BLOCKED gates.
