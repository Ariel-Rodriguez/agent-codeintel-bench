# agent-codeintel-bench

Coding-agent extensions are usually adopted on marketing claims, not evidence.
This repo is our independent test bench: it runs the same task with and without a
candidate, under isolation, and measures correctness and cost. We use it to decide
whether a candidate actually helps — and whether it helps *our* setup — before
adopting it.

**Results:** <https://ariel-rodriguez.github.io/agent-codeintel-bench/>

## How it works

Two comparisons, two questions:

| Comparison | Baseline | Candidate | Question |
|---|---|---|---|
| Scientific | vanilla Pi | vanilla Pi + candidate | Does the candidate help at all? |
| Adoption | our configured Pi | our configured Pi + candidate | Does it help *our* setup? |

A scientific win does not imply adoption. Each condition runs in a fresh
container with no network egress, sequentially and counterbalanced. Correctness is
checked by real tests host-side; treatment activation is verified from
instrumentation, never assumed. Missing config or unverified activation fails
closed.

## Run one

```bash
export CONDITIONS_FILE="$PWD/experiments/dual-baseline.json" \
       CORPUS=<repo> TASKS=<benchmarks> OUT="$PWD/out" RUN_ID=candidate-1 TRIALS=6 \
       DUAL_IMAGE=<image> PI_PROVIDER=<p> PI_MODEL=<m> UPSTREAM_BASE_URL=<model-origin>
harness/run_isolated.sh
python3 harness/compare.py --results out --run-id candidate-1 --conditions "$CONDITIONS_FILE"
```

## Where to go

| I want to… | Go to |
|---|---|
| Understand the framework | [`docs/dual-baseline.md`](docs/dual-baseline.md) |
| Write a report | [`docs/format.md`](docs/format.md) |
| See a finished run | [`docs/runs/kernel-6x2.md`](docs/runs/kernel-6x2.md) |
| Run in the isolated container | [`docker/README.md`](docker/README.md) |
| Add a tool / adapter | [`harness/adapters.md`](harness/adapters.md) |
| Check a tool for risky behaviour | `python3 harness/scan_extension.py <tool>` · `docker/run.sh probe` |
| Let an agent do it | [`PROMPT.md`](PROMPT.md) |
| Contribute / commit rules | [`CONTRIBUTING.md`](CONTRIBUTING.md) |

Older single-candidate reports and the legacy runner are under
[`archive/`](archive/) for provenance.

## License

MIT — see [`LICENSE`](LICENSE).
