# Agent bootstrap prompt

> Give a coding agent this file plus a candidate repository/extension to evaluate.
> Discover → Inspect → Reproduce → Benchmark → Challenge → Decide → Track.

Evaluate the candidate independently in this repository, **not in our daily-use
Pi installation**. Trust measurements, not vendor claims or popularity.

## Steps

1. **Assess before changing anything.** Read `CONTRIBUTING.md`, `README.md`,
   `harness/adapters.md`, `docs/dual-baseline.md`, `docs/format.md`, and the latest
   reports/commits/results. State existing capabilities, genuine gaps, smallest
   changes, and incompatibilities. Prefer the existing manifest/isolation path.
2. **Inspect the candidate.** Use the supplied repository or `inputs/tool/`.
   If absent, stop as blocked. Record its exact revision, requirements, claims,
   configuration switches and local patches. Inspect source, run
   `python3 harness/scan_extension.py inputs/tool`, and provision dependencies
   explicitly in an offline-capable benchmark image. Never install into the
   owner's actual Pi. External positive/negative reports are prior hypotheses,
   not our measured findings; do not automatically queue RTK or another tool.
3. **Pre-register hypotheses and tasks.** Separate spontaneous tool selection
   from search effectiveness when deliberately exercised. Use existing task
   families and executable repair verification where possible. References,
   hidden tests and metrics specifications stay host-side. Select relevant short
   and long workloads; do not add a new benchmark family without necessity.
   Open the claim issue required by `CONTRIBUTING.md` before real trials.
4. **Freeze both baselines.** Start from `experiments/dual-baseline.json`.
   Use arbitrary condition IDs with declared scientific and adoption pairs.
   Curate and owner-review a sanitized personal snapshot: exact Pi/model/thinking,
   ordered pinned extensions/assets, tools, supported settings, non-secret env,
   activation contracts, configuration hash, and limitations. Freeze with
   `python3 harness/baseline.py curated.json frozen.json` and embed its descriptor.
   Do not read/copy a home directory, credentials, sessions, or arbitrary personal
   files into artifacts. If the actual setup cannot be safely reproduced, leave
   adoption blocked; do not replace it with a simulation and call it personal.
   Candidate conditions **inherit** each baseline plus the same candidate payload.
5. **Prove compatibility and execution.** Capture a no-network probe using the
   exact production flags and loading order. Prove required implementations,
   settings, registration and actual tool/hook execution, not just successful
   import. Review wrapper conflicts. Use the existing Kernel audit verifier when
   applicable, or the documented source-reviewed activation sidecar contract.
   Every real candidate cell needs its own evidence. Missing proof is invalid,
   not an efficiency win. Preserve supported mechanism ablations separately.
6. **Validate cheaply first.** Run
   `python3 -m unittest discover -s harness/tests`. Use synthetic traces/small
   fixtures to check controls, analysis and fail-closed paths. These tests do
   **not** establish real compatibility or performance. Obtain explicit approval
   before expensive model/Docker benchmark trials.
7. **Run approved comparisons sequentially** through `harness/run_isolated.sh`
   with `CONDITIONS_FILE` set. See `docs/dual-baseline.md` for the commands.
   Four conditions use a four-trial balanced schedule (eight for replication).
   Pin the model service revision, images, repository and task assets. Never
   overwrite attempted cells. Do not alter prompts/settings mid-experiment.
8. **Challenge the result.** Inspect failed/invalid cells, executable scoring,
   activation, wrapper conflicts, per-trial paired deltas and spread. Keep each
   task/model stratum separate. Report input/output/total tokens, wall, calls,
   tool use, repeated retrieval and unavailable instrumentation. Fewer bytes per
   operation do not imply lower end-to-end cost. Report 0005 observed a token
   regression, but one repeated read and zero post-truncation retrieval events
   do not establish repeated retrieval as its primary cause.
9. **Report two independent verdicts** using `docs/format.md`:
   scientific (candidate vs vanilla) and adoption (candidate vs actual configured
   Pi). Use Adopt / Adopt selectively / Experimental / Reject / Insufficient
   evidence / Blocked or invalid. Automated positive screens remain Experimental;
   justify any promotion with repeated practical benefits, no demonstrated
   correctness regression, and relevant workload coverage. Equal ceiling scores
   are not proof of equivalent correctness on harder tasks. Distinguish rubric
   from executable-test evidence. Do not pool heterogeneous tasks or invent USD
   costs for local models. Link `comparisons.json`, raw evidence and provenance.
10. **Track without deploying.** State limitations and smallest next step. Update
    only the new report, not earlier conclusions. Follow the exact local commit
    policy (`Fix|Add|Chore`, no co-author/generated trailers). Do not push/merge
    without separate permission. Actual adoption/enabling requires a separate,
    explicit owner decision, never an automatic consequence of a verdict.

## Rules

- Never commit credentials, `configs/`, `work/`, `out/`, `results/`, or `inputs/`.
- Missing prerequisites are blocked, never measured success.
- Distinguish unverified compatibility from a demonstrated defect.
- Do not modify fixtures/tests/references to make a candidate pass.
- Publish only reviewed sanitized material; raw traces may contain private code.
