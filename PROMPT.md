# Agent bootstrap prompt

> Point a coding agent (Pi) at this file to autonomously set up and run one
> code-intelligence A/B test. It is written to be pasted as the first prompt:
>
> ```bash
> pi "$(cat PROMPT.md)"
> ```

You are setting up and running a code-intelligence A/B test in this repository.

## Steps

1. **Understand the repo.** Read `README.md`, `CONTRIBUTING.md`,
   `harness/adapters.md`, and the reports under `docs/` (start with `docs/index.md`). Inspect `harness/` and `benchmarks/`.
2. **Inspect the inputs.** Look under `inputs/`:
   - `inputs/repo.zip` or `inputs/repo/` — the repository to test (if absent,
     use the bundled fixture `fixtures/widget-service`).
   - `inputs/tool/` — the Pi extension or tool to test (if absent, report that
     no tool was provided and stop).
   Determine the adapter: the `pi -e` path for an extension, and the `--tools`
   glob for its tools. Record the tool's revision (git sha or version).
3. **Scan the tool before running it.** Run `python3 harness/scan_extension.py
   inputs/tool` (or `docker/run.sh probe`). Record the findings. The bench
   container has no direct network egress; say so in the report.
4. **Set up baseline vs experiment** with the setup script:

   ```bash
   harness/setup_test.sh --repo inputs/repo.zip --tool inputs/tool \
     --tool-tools 'read,bash,edit,write,<tool-prefix>_*'
   source work/experiment.env
   ```

   Register the test by opening a **Claim a test** issue before running.
5. **Define the tasks.** If the repo is the bundled fixture, the tasks in
   `benchmarks/` already apply. Otherwise, derive answers independently (grep,
   reading code — not from a model) and add one directory per task family with
   `prompt.md` and `reference.json`. Cover navigation, impact, repair, and
   cross-session persistence where the repo allows.
6. **Run** at least 3 counterbalanced trials, sequentially:

   ```bash
   for r in run1 run2 run3; do harness/run_suite.sh "$r"; done
   harness/evaluate.py run1 run2 run3
   ```

7. **Verify the tool was used.** For each enhanced run, parse the system prompt
   and `tool_execution_*` events. If the tool was never visible or called, say so
   — do not report a result as if the treatment were applied.
8. **Report.** Summarise quality and speed per task family, with raw paths,
   limitations, and an explicit verdict. Commit with an `Add`/`Fix`/`Chore`
   message and comment the result on the claim issue.

## Rules

- Never commit credentials, `configs/`, `work/`, `results/`, or `inputs/`.
- A missing prerequisite is reported as blocked, never as a result.
- Separate "could not verify" from "defect".
- Do not modify the bundled `fixtures/` or `benchmarks/` to make a run pass.
