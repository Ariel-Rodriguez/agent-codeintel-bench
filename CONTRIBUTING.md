# Contributing

## Commit messages

Every commit's first line must be exactly:

```
<Fix|Add|Chore> <short description>
```

- `Fix` — correct a defect.
- `Add` — introduce a capability, file, or test.
- `Chore` — maintenance that is neither (pins, docs, tooling).

Rules:

- Imperative mood, capitalized verb, no trailing period, ≤ 72 characters.
- **No co-author trailers and no generated-by lines** (`Co-Authored-By:`,
  `Generated with ...`, `🤖`). Commits must stand on their own.
- One logical change per commit.

A `commit-msg` hook enforces this. Enable it once per clone:

```bash
git config core.hooksPath .githooks
```

## Claiming a test

A *test* is one `(tool revision × task family × repo/fixture × model)` cell. To
avoid duplicated effort:

1. **Open an issue** using the **Claim a test** template
   (`.github/ISSUE_TEMPLATE/claim-test.md`), title `[claim] <tool> — <task> on <repo>`.
2. Add the `claim` label and assign yourself.
3. A claim is valid for **14 days**. Comment to renew; a stale claim may be
   released.
4. Post results as a comment on the issue, linking the run directory and its
   `metrics.json`, plus a new or updated report under `docs/reports/`.
5. Close the issue when the finding is committed.

Do not open a second claim for an open `(tool, task family, repo)` cell. If you
disagree with a claimed result, open a normal issue describing the discrepancy
and reference the claim.

## Adding a tool

1. Read [`harness/adapters.md`](harness/adapters.md).
2. Pin the exact revision you test; record it in the issue and in
   `findings/` with the run.
3. Only the enhanced arm loads the tool. Baseline stays `read,bash,edit,write`.
4. Prove the tool was **used**, not merely installed: parse the system prompt and
   `tool_execution_*` events in the raw stream.
5. Run at least 3 counterbalanced trials before reporting a delta.
