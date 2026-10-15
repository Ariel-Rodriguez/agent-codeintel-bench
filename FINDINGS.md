# Findings

The first tool tested is a local structural code-index extension for Pi
(`pi-codeindex`, revision pinned at test time). It registers ~14
`codeindex_*` tools (search, def, callers, callees, refs, implementers,
supertypes, impact, files, explore, match, cycles, status, sync) backed by a
per-repo SQLite index. The baseline arm has only `read, bash, edit, write`.

## Method

- **Two arms, one difference:** baseline (`read,bash,edit,write`) vs enhanced
  (same built-ins plus the extension, loaded with an explicit `pi -e <path>`).
- **Counterbalanced:** each run executes baseline and enhanced in alternating
  order; reported point estimates are over 3 paired trials per task and model.
- **Sequential, one condition at a time**, to avoid the shared-host noise of
  concurrent runs.
- **Reference corpus:** a private Python service (identifiers withheld). The
  package shipped in `fixtures/widget-service` is a neutral stand-in with the
  same task shape, so the harness and prompts are reproducible without the
  private source.
- **Evidence:** every run stores the prompt and its SHA-256, `git` status before
  and after, the full JSONL event stream, wall time, provider-reported usage and
  tool calls. See `harness/` and `results/`.
- **Tool actually used?** Verified per run by parsing the system prompt
  (`message_start.message.sections.tools`) and counting
  `tool_execution_start`/`tool_execution_end` events. Installing a tool is not
  evidence that the model saw or used it.

## Results

Scores are per-task: navigation 7 points, impact 5, repair 4, persistence 3.

| task (n=3 unless noted) | model | arm | quality | input tokens | wall time |
|---|---|---|---|---|---|
| navigation | deepseek-flash | baseline | 21/21 | — | — |
| navigation | deepseek-flash | enhanced | 20/21* | **+9.3%** | −2.4% |
| navigation | Qwen3.8-27B 224k | baseline | 21/21 | 5508 | 20.5 s |
| navigation | Qwen3.8-27B 224k | enhanced | 21/21 | **−18.7%** (mixed) | +15.5% |
| impact | deepseek-flash | baseline | 15/15 | — | — |
| impact | deepseek-flash | enhanced | 15/15 | **+66.7%** (outlier) | +14.4% |
| impact | Qwen3.8-27B 224k | baseline | 15/15 | 7228 | 19.2 s |
| impact | Qwen3.8-27B 224k | enhanced | 15/15 | **−53.7%** (3/3) | −3.3% |
| repair (n=1) | deepseek-flash | baseline/enhanced | 4/4 / 4/4 | — | 23.9 / 17.7 s |
| repair (n=1) | Qwen3.8-27B 224k | baseline/enhanced | 4/4 / 4/4 | — | 45.4 / 60.4 s |
| persistence (n=1) | deepseek-flash | baseline/enhanced | 3/3 / 3/3 | — | 107.6 / 91.2 s |
| persistence (n=1) | Qwen3.8-27B 224k | baseline/enhanced | 3/3 / 3/3 | — | 113.2 / 120.8 s |

\* The single non-perfect score is a scoring artifact: the enhanced answer was
correct but omitted one expected literal token. Hand review gives both arms 7/7.

## What the evidence shows

1. **No correctness benefit.** Every baseline/enhanced pair scored identically.
   The extension did not make the agent more accurate on navigation, impact
   analysis, repair, or cross-session recall.
2. **Cost effect is model-dependent.** On `deepseek-flash` the enhanced arm was
   *more* expensive on input tokens (navigation +9.3%, impact +66.7%, the latter
   driven by one 23k-token run). On the local Qwen model it was *cheaper* on the
   impact task in all 3 trials (−53.7% input, −3.3% wall) because a single
   `codeindex_def` result replaced several large `grep`/`read` dumps. Navigation
   was mixed (−18.7% mean but two of three trials went up).
3. **Repair did not use the tool.** In both repair trials the enhanced arm made
   **0** `codeindex_*` calls and fixed the bug with ordinary file reads.
4. **Persistence is real but narrow.** After a source change the enhanced arm's
   on-disk index went stale (`status --verify` reported `changed: 1`). The
   agent-facing `status` tool exposes **no** verify option, so the agent could
   only blindly re-`sync`. Both arms still answered the stage-2 questions
   correctly, and the baseline **re-explored** — so index persistence did not
   translate into a measurable win.
5. **Adoption verdict:** not justified. A ~54% context reduction on one task
   family, under one model, with no correctness gain, does not outweigh adding a
   per-repo index and a stale-state footgun.

## Threats to validity

- **Small n.** 3 paired trials per task (1 for repair/persistence); provider
  nondeterminism and caching dominate the effect sizes.
- **Keyword scoring.** The reference rubric matches substrings; it produced at
  least one false negative. It should be replaced with independent hidden tests.
- **Contamination.** The private-corpus reference answers were readable by the
  same OS user as the agent; in the persistence task one arm read them. Treat
  the persistence numbers as "not clean evidence".
- **Not an access boundary.** Running arms in separate directories is not
  sandboxing.
- **One tool, one revision.** Results hold only for the pinned revision tested;
  a patched tool is a different treatment.
