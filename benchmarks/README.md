# Benchmarks

Four task families, each with a machine-readable `reference.json` used by
`harness/evaluate.py`. All prompts target `fixtures/widget-service` and contain
no identifiers from any private corpus.

| id | family | what it measures |
|---|---|---|
| `navigation` | Symbol + consumer lookup | Does the tool reduce exploration cost/errors when locating a symbol and its callers/exports/tests? |
| `impact` | Rename impact analysis | Does the tool identify the exact definition/export/test files affected and correctly prove nothing outside the package changes? |
| `repair` | Bug repair | Does the tool help find the root cause of a failing test and apply the minimal correct fix? |
| `persistence` | Cross-session reuse | Does on-disk tool state (e.g. an index) answer follow-up questions in a **new** session better than a fresh agent? |

Prompts are deliberately answer-neutral: they ask for evidence and for explicit
"unknown" when a fact cannot be verified.

`repair/bug.patch` is applied identically to both arms before the repair task, so
the two arms start from the same failing commit.
