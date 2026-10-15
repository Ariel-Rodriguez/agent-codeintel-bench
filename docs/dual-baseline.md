# Dual-baseline evaluation

The manifest runner is the preferred foundation. No new scheduler, sandbox or
scorer is introduced. Old two-arm mode and `experiments/kernel-retrieval.json`
remain unchanged; legacy A/B/C ordering and summaries are preserved.

## Two questions, not one leaderboard

- **Scientific:** vanilla Pi vs vanilla Pi + candidate. Only the candidate changes.
- **Adoption:** our frozen configured Pi vs that same setup + candidate.

An improvement against vanilla is not automatically an adoption recommendation.
Keep task/model strata separate; do not average unrelated rubric scores or costs.
Report 0005's compression-OFF result is worth investigating separately from
compression ON. Neither the observed token regression nor search non-use proves
its proposed mechanism. External RTK reports are prior evidence to investigate,
not a result established here or a reason to automatically queue/install RTK.

## Manifest additions (opt-in)

See [`../experiments/dual-baseline.json`](../experiments/dual-baseline.json).
**It is a blocked template, not a snapshot of the owner's actual setup.** Its
candidate paths/hashes/revision are placeholders and its personal provenance is
explicitly unreviewed/non-actual. No new real experiment has been run.

The existing `limits` and condition IDs are retained. For explicit comparisons:

```json
{
  "comparisons": [
    {"id": "scientific", "baseline": "vanilla", "candidate": "vanilla_candidate"},
    {"id": "adoption", "baseline": "personal", "candidate": "personal_candidate"}
  ]
}
```

IDs are arbitrary. An alternative comparison ID needs `purpose: scientific` or
`purpose: adoption`. Declare one or both pairs. Each baseline condition contains
`id`, `image`, and a frozen `snapshot: {sha256, data}`. Each candidate condition
contains **only** `id` and `inherits: <baseline-id>`; overrides, recursive
inheritance and missing parents are rejected. One top-level `candidate` declares
an ordered addition: pinned `extension`, additional `tools`, `env`,
`guidance_files`, and its `activation` contract. Both pairs use that same payload.
Candidate env may not change existing baseline values. Every condition belongs
to an explicit pair. `baseline_differences` documents vanilla/personal differences.

A pair inherits the **same image**, Pi version, model/thinking, configuration,
limits and baseline identity. Provision candidate dependencies into that image
beforehand; only candidate conditions load it explicitly. This deliberately
rejects image changes as an uncontrolled second treatment. Vanilla and personal
may differ from each other, including model settings; interpret each pair only
within its own fixed model. Images must already exist locally, with no pull/build
inside trials. All snapshot extensions load by repeated `-e` in declared order;
all guidance files by repeated `--append-system-prompt` in declared order.

Four conditions use a balanced Latin-square schedule (4 trials, each condition in
each position once and each pair in both orders twice); 8 repeats the schedule.
Arbitrary even counts use N/2N trials; odd counts use 2N or an N-trial
position-balanced pilot. The historical ABC/BCA/CAB/ACB/CBA/BAC stays exact.

## Freeze a real personal baseline safely

1. Manually inventory relevant settings with the owner's permission. **Do not
   export the home/agent directory.** Identify exact Pi and provider/model/thinking;
   enabled tools; ordered extensions with full commit SHA or exact version;
   reviewed settings/env; and sanitized guidance assets. Provision assets under
   `/opt` in the image with locked dependencies. Review pinned source and patches.
2. Build a curated snapshot matching the example's `snapshot.data`. Extension
   entries and guidance require exact SHA-256 hashes. The image digest identifies
   the complete dependency/source tree; entry hashes alone do not establish full
   source identity. Record build/source revision evidence in the report.
3. `model_config_sha256` pins `models.json` **after** the container's gateway
   rewrite, or is null if absent. Provision this model configuration separately;
   never embed credentials in it or publish it without review. Authentication,
   if needed, stays in an explicitly supplied private `PI_AUTH_DIR`/`auth.json`,
   outside snapshots and published artifacts. Only the config hash is recorded.
4. Set `provenance.actual_personal: true` only for an actual reproduced personal
   setup, `reviewed: true` after sanitization/compatibility review, and list all
   limitations. Non-actual, unreviewed or limited snapshots block their pair.
   A human attestation is not automatic discovery or proof of equivalence.
5. Freeze the curated JSON explicitly (the command never scans personal files):

   ```bash
   python3 harness/baseline.py curated.json frozen.json
   ```

   This outputs a canonical SHA-256 descriptor and refuses overwriting it. Embed
   the descriptor in the baseline condition. Any change needs a new hash/review.

Supported settings are deliberately narrow: `compaction.enabled/reserveTokens/
keepRecentTokens`, `retry.enabled/maxRetries/baseDelayMs`, and `thinkingBudgets`
for minimal/low/medium/high. Unknown settings/asset fields are rejected, not
silently ignored. Snapshot env is literal, non-secret and cannot override harness
or Pi controls. Settings are written only in a harness-owned agent directory,
never the daily-use configuration. Explicit model flags override ambient env.

MCP, automatic packages, skills, discovered instructions, arbitrary native config
files, complex wrapper composition and other settings are **not** reproduced by
this milestone. If relevant to the actual environment, document the limitation
and block adoption rather than omit them and claim it represents the owner.
GUI-only preferences can be documented as irrelevant to the one-shot evaluation.
No sanitizer can recognize every secret embedded in arbitrary text: manual review
of literals, source evidence and guidance remains mandatory.

## Activation evidence

Keep the existing Kernel implementation audit and `verify_wrappers.py` intact.
For a snapshot extension, its ordered activation contract identifies `id`, exact
`revision`, `registered_tools`, `executed_tools`, `hooks`, effective `settings`,
and `source_evidence` (reviewed source locations and instrumentation patch hash).
At least one tool or hook must execute. Distinguish registration/tool selection
from forced effectiveness trials when choosing requirements.

For general extensions capture `activation.jsonl` privately through reviewed
instrumentation (never return it as model-visible tool content). Each record has
`id`, `revision`, `settings`, and `conflicts: []`. Required records:

- Exactly one `phase: loaded`, with `registered_tools` exactly as declared.
- For every required tool: `phase: execute`, `tool`, `toolCallId`, `success: true`.
  Join it to actual successful start/completion events in `stdout.jsonl`.
- For every required hook: `phase: hook`, `hook`, `success: true`, emitted only
  after the hook actually executes, not at registration.

Wrong implementation/revision/settings, missing execution, unknown implementation
records or reported wrapper conflicts invalidate the cell. Overlapping declared
tool wrappers are rejected until their composition can be source-verified; do not
assume last-loaded wins safely. A no-network production-flags compatibility probe
is a separate prerequisite; synthetic traces do not establish real Pi support.

To reuse Kernel's existing `wrapper_audit.jsonl` instead of adding another
execution sidecar, add `wrapper_capture: {instrumentation, wrapper_implementations}`
to the extension activation contract. These are the same fields used by the old
condition schema. Set `registered_tools` equal to `executed_tools` (the wrappers
whose execution proves availability), with no hooks. The evaluator delegates to
`verify_wrappers.check_capture`: joined entry/completion, exact implementation,
revision, effective compression/retrieval settings, pre/post bytes/hashes and
model-visible output. Other registration checks belong in the compatibility
probe. Use full pinned revision IDs consistently in new snapshots/audits.

**Trust boundary:** neither old nor new verifier authenticates arbitrary
agent-writable JSON. Real evidence needs trusted capture paths, source-reviewed
instrumentation and independent compatibility/conflict review. A malicious
extension can fabricate a sidecar; do not treat passing schema checks as proof
of honesty. Do not weaken the existing Kernel checks to accommodate a candidate.

## Approved execution and offline analysis

First run synthetic/unit checks (no model/Docker trials):

```bash
python3 -m unittest discover -s harness/tests
```

After explicit approval, with a curated manifest, local pinned image and task
assets ready:

```bash
export CONDITIONS_FILE="$PWD/experiments/my-candidate.json" \
       CORPUS="$PWD/fixtures/widget-service" TASKS="$PWD/benchmarks" OUT="$PWD/out" \
       RUN_ID=my-candidate TRIALS=4 TASK_LIST="repair_retrieval_small repair_retrieval_long" \
       DUAL_IMAGE=my-preprovisioned-image SCORING_IMAGE=my-trusted-scoring-image \
       UPSTREAM_BASE_URL=<approved-model-origin>
harness/run_isolated.sh
```

No auth/home snapshot is created. The existing optional private runtime auth
mount is unchanged. Missing config, images, assets, hashes or version pins block
execution. Every cell still receives only its broken corpus, one prompt,
resolved condition, and its own output mount. Host-only executable repair scoring
uses the trusted image, not a candidate's scorer.

The runner writes an exclusive `out/<RUN_ID>/run_plan.json` declaring expected
trials/tasks, resolved conditions, original manifest hash, corpus identity, and
prompt/task-asset hashes (including host-only verification). Changed corpus or
task assets abort execution. Attempted cells/plans are never overwritten. Partial
runs retain evidence and must not be interpreted as complete experiments.

Evaluation uses existing scoring. Snapshot runs additionally require complete
termination/final-response evidence, matching runtime flags/settings/pins and
activation. Missing token usage is unavailable, not zero. Limits remain scored
failures if treatment execution was verified. Raw outputs/errors are retained.

Re-analyze without any model/Docker calls:

```bash
python3 harness/compare.py --results out --run-id my-candidate \
  --conditions experiments/my-candidate.json
```

`comparisons.json` and `comparisons.md` provide independent verdicts, per-task
correctness/evidence level, input/output/total tokens, wall time, tool calls/use,
repeated retrieval and output bytes. JSON includes every planned trial's paired
absolute/relative deltas, mean/population SD/range, missing metrics, invalid or
absent cells and their captured resources. No heterogeneous-task aggregate or USD
price is invented. Analysis checks provenance and activation again, compares
paired controls and rejects across-trial drift. A missing plan/changed manifest
fails closed; a bad adoption pair does not erase valid scientific evidence.

## Verdict policy

The automated, transparent screening rule is intentionally conservative:

- Any absent, uncontrolled, incomplete or unverified cell blocks its comparison.
- Any paired correctness regression rejects general adoption, even if cheaper.
- Fewer than three complete pairs or missing token/wall metrics: insufficient.
- A practical total-token reduction in **every** trial (default 10%), with no
  wall regression above that threshold and no correctness regression, receives
  **Experimental**, not automatic Adopt.
- A repeatable practical token regression receives Reject on that workload.
- Mixed efficiency results remain workload-dependent, with all task verdicts
  visible, never hidden behind an overall score.

A reviewed report can promote Experimental to **Adopt** or **Adopt selectively**
only with repeated practically meaningful benefit on relevant workloads, no
observed correctness regression, compatibility/conflict review and appropriate
limitations. Equal easy-task success is not equivalence on harder tasks. Keep
scientific and adoption verdicts separate. An adoption recommendation never
installs/enables the candidate; that requires a separate explicit owner decision.
