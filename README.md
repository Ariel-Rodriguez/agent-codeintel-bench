# agent-codeintel-bench

**ELI5:** coding agents find code with `grep` and by reading files. Some tools
claim to do that better (code indexes, symbol search, LSP, embeddings). This repo
tests that claim honestly: the **same task, two agents** — one plain, one with the
tool — then compares correctness and cost. Untrusted tools run in a locked-down
Docker box with **no internet egress**, so a bad tool cannot phone home.

**Results live on the website:** <https://ariel-rodriguez.github.io/agent-codeintel-bench/>

## Where to go next

| I want to… | Go to |
|---|---|
| Read the results | [website](https://ariel-rodriguez.github.io/agent-codeintel-bench/) · [`docs/index.md`](docs/index.md) |
| Write a report in the standard format | [`docs/format.md`](docs/format.md) |
| See the reports | [`docs/reports/`](docs/reports/) (0001 concluded, 0002 blocked) |
| Run a test in the isolated container | [`docker/README.md`](docker/README.md) |
| Add a new tool to test | [`harness/adapters.md`](harness/adapters.md) |
| Bring my own repo + tool | [`harness/setup_test.sh`](harness/setup_test.sh) |
| Check a tool for risky behaviour | `python3 harness/scan_extension.py <tool>` · `docker/run.sh probe` |
| Measure how big a repo is | `python3 harness/repo_complexity.py <repo>` |
| Let an agent run the experiment | [`PROMPT.md`](PROMPT.md) |
| Contribute / claim a test / commit rules | [`CONTRIBUTING.md`](CONTRIBUTING.md) |

## In one line

`baseline (read,bash,edit,write)` vs `enhanced (+one tool)`, four task families,
counterbalanced trials, every number backed by a stored run.

## License

MIT — see [`LICENSE`](LICENSE).
