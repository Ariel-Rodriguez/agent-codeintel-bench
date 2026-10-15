# Retrieval repair pair — draft, not frozen

Both tasks use `fixtures/widget-service`. `fixture.patch` introduces public
regressions/tests and an offline deterministic runner. `reference.patch`,
`hidden_tests/`, `verify.json`, and `metrics.json` are **host-only**. Never mount
the task directory; the runner stages only the public patched corpus and prompt.
All task/reference generation code and host tests are excluded from agent images.
Regenerate public/reference patches with `python3 harness/build_retrieval_tasks.py`.

- **long:** three production files regress explicit millisecond normalization,
  observation-scoped replay identity, and terminal/durable refusal logging.
  Real route/reducer/log scenarios emit a deterministic trace. An actual mismatch
  produces `OBS_TS_UNIT_MISMATCH` in the middle of the timestamp scenario trace;
  the ordinary scenario/test summary does not repeat that token. A focused
  `python3 tools/run_suite.py --focus timestamp` exposes it in short output.
  Other episodes expose replay and terminal-log diagnostics. No assumption is
  made that Kernel wraps bash.
- **small:** one future-skew comparison regresses in freshness.py. Its default
  suite output is short. It uses exactly the same conditions and corpus.

## Offline host validation performed

`python3 -m unittest discover -s harness/tests` validates both broken fixtures,
reference repairs, all seven incomplete long repair combinations, authorize-all
and refuse-all bypasses, patch/untracked test tampering, unsafe archives, and
hidden-test overlay order. Hidden checks exercise each defective module
independently as well as the integration flow. Neither blanket bypass passes.

On host Python 3.9.6 (no third-party dependencies/network):

| reconstruction | result | suite count |
|---|---|---:|
| long broken, public + trusted hidden | FAIL (9 failures, 1 error) | 24 |
| long reference, public + trusted hidden | PASS | 24 |
| small broken, public + trusted hidden | FAIL (2 failures) | 16 |
| small reference, public + trusted hidden | PASS | 16 |

The public broken long invocation produced about **32 KB**; the focused timestamp
invocation about **1.8 KB**, each containing the primary diagnostic once. The
public small broken invocation was about **0.45 KB**. Exact traceback sizes vary
with workspace path/platform; scenario ordering/data contain no random seeds or
wall-clock measurements. These are raw host output measurements, **not** a
validated Pi truncation boundary or a Kernel compression contrast.

## Precise BLOCKED gates before trials

1. Supply Kernel `b9e93be` source/instrumented image and establish B's actual full
   settings and C's supported independent switch (or keep C blocked).
2. Validate Pi 1.2.0 event schema and actual built-in-name wrapper execution with
   the offline production probe and real-cell audits.
3. Pilot raw/pre/post diagnostic visibility. It must survive native Pi delivery
   yet be omitted by B and retained by C. If shell shaping is absent or this
   contrast cannot be established, add/pilot a long-source-read exposure; the
   verbose suite alone is shell-overhead stress, not compression evidence.
4. Inspect excluded pilot traces for multiple inspect–edit–test cycles. If the
   task collapses to one repair cycle, redesign before freezing. No model pilot
   or compression exposure is claimed by these offline tests.

Trusted container scoring (`--network none`) and end-to-end trials were not run
in this pass. Rebuild base/tool images so old embedded fixture materials cannot
leak a reference repair. Do not describe these tasks/manifest as trial-ready.
