# Retrieval trace metrics (host only)

`evaluate.py --results out --references benchmarks --label RUN [--conditions FILE]`
writes each cell's `metrics.json` and `tool_metrics.jsonl`, plus a run summary.
Without a manifest it discovers condition directories (legacy arms still work).
Every existing cell is retained, including invalid/blocked cells and their costs.
Nonzero executions are infrastructure-invalid unless a recorded wall/output limit
establishes a valid task failure. Missing scoring evidence never becomes success.

Calls join on `toolCallId`; completed `toolResult` text wins over execution-end
text. Only text blocks count (UTF-8 bytes). Turns count completed assistant
messages. `tool_metrics.jsonl` retains arguments, order, source, sizes,
repetition/mutation labels and explicit truncation evidence, not duplicate output.
Raw traces remain the source of output text. `tool_calls_total` counts starts or
completed fallback calls, not unexecuted assistant requests; requests are retained
separately in `tool_calls_requested`. Repetitions use successful calls;
response size counts delivered errors too. Overlap is requested, bounded lines,
not returned lines; omitted limits remain a separate DEFAULT range. Concurrent
or unclassified shell activity yields mutation-unknown, not no-mutation.

`response_metrics(..., tokenizer=...)` accepts only a preinstalled offline
object with `identity` (a pinned name/revision) and `encode(text)`. No tokenizer
is bundled or downloaded: token estimates are null by default. These estimates
are NOT billable usage. Existing message usage/cost fields remain independent.
Distributions use nearest-rank p95. By-tool distributions prevent pooling across
a changing call mix; per-call arguments allow host-side operation matching.

Task `metrics.json` can declare `workspace`, `pi_version`, version-pinned
`truncation_markers: [{pi_version, text}]`, and host-only
`diagnostics: [{id, text}]`. Only boolean `truncated`/`isTruncated` metadata or
explicitly pinned markers establish truncation. Missing evidence is unknown.
Five-turn post-truncation links are associations, not causal recovery claims;
test reruns are counted separately, not classified as retrieval recovery.
Diagnostic episodes require captured `pre_text` and `post_text` in completion
audit records and actual absence in delivered text. Unrecovered episodes remain
right-censored; without captured pre/post audit evidence and diagnostic definitions
their count is null, not zero. `diagnostic_audited_calls` exposes evidence coverage.

Wrapper identity requires sidecar `wrapper_audit.jsonl` enter AND complete
records joined to a real call ID/tool with matching `implementation_id` and
`revision` and a boolean completion `success`. Registration/tool names do not
prove execution. `expected_activation.wrapper_tools` gates validity for new
conditions; `code_search` calls and audited executions are reported separately.
See `adapters.md` for source-dependent limitations. Audit production and pinned
Pi schema compatibility must be validated before using these metrics to make
claims about real Kernel behavior. Synthetic unit traces are not that validation.
