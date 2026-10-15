# agent-codeintel-bench

A small, reproducible harness for **A/B testing code-intelligence tools for
coding agents** (Pi extensions, MCP servers, LSP bridges, custom tool sets).

Coding agents already navigate code with `grep`, file listing, and `read`. Many
code-intelligence tools promise better navigation, impact analysis, repair, and
cross-session reuse. This repo exists to *test* that promise instead of assuming
it — and to make it easy to add the next tool.

The first measured result is in [`FINDINGS.md`](FINDINGS.md): a structural
code-index extension produced **no correctness benefit** and a
**model-dependent** token effect across four task families.

## How it works

```
fixtures/widget-service/     neutral Python package used as the corpus
benchmarks/                  four task families, each with prompt + reference.json
harness/                     prepare / run / evaluate scripts (tool-agnostic)
configs/                     isolated Pi configs per arm (auth.json is gitignored)
results/                     raw JSONL streams, metrics, per-run reports
work/                        the two working copies the agents actually edit
```

- **Baseline arm:** `read, bash, edit, write`.
- **Enhanced arm:** the same built-ins **plus one tool** (`CODEINTEL_EXT` /
  `ENHANCED_TOOLS`). Adding a tool is described in
  [`harness/adapters.md`](harness/adapters.md).
- **Task families:** `navigation`, `impact`, `repair`, `persistence`.
- **Evidence per run:** prompt + SHA-256, `git` status before/after, the full
  JSONL event stream, stderr, exit code, wall time, provider token usage, and
  tool calls by name.

## Quickstart

### Isolated (recommended)

Because a code-intelligence extension runs inside the Pi process, treat it as
untrusted. Run it in the container, which exposes only `inputs/` (read-only) and
`out/`:

```bash
mkdir -p inputs
cp /path/to/repo.zip inputs/repo.zip     # the repository to test
cp -R /path/to/tool    inputs/tool        # the extension/tool to test

docker/run.sh build
docker/run.sh run      # prepare + run + write results to out/
docker/run.sh down     # tear down (containers and volumes)
```

See [`docker/README.md`](docker/README.md) for credentials and network options.

### Local

```bash
# 0. prerequisites: pi on PATH, python3, git; network for the first pip install
git clone <this repo> && cd agent-codeintel-bench
export PI_PROVIDER=deepseek PI_MODEL=deepseek-flash PI_THINKING=high

# 1. create two identical work copies + isolated Pi configs (copies your auth.json)
harness/prepare.sh

# 2. point "enhanced" at a tool (optional; without this it is baseline vs baseline)
export ENHANCED_TOOLS='read,bash,edit,write,codeindex_*'
export CODEINTEL_EXT="$PWD/vendor/pi-codeindex/src/pi/index.ts"

# 3. run one counterbalanced suite
harness/run_suite.sh run1

# 4. summarise
harness/evaluate.py run1
```

Each `run_condition.sh` invocation writes to
`results/<run_id>/<arm>/<task>/`. `evaluate.py` writes `metrics.json`,
`results/summary.csv`, and a per-run `REPORT.md`.

### Repair fixture

The repair task needs the bug applied first:

```bash
for arm in baseline enhanced; do
  git -C "work/experiment-$arm" apply benchmarks/repair/bug.patch
done
harness/run_condition.sh baseline run1 repair benchmarks/repair/prompt.md
harness/run_condition.sh enhanced run1 repair benchmarks/repair/prompt.md
```

The fixture ships a passing test suite; the patch makes exactly one test fail.

### Persistence (two sessions)

```bash
harness/run_condition.sh baseline run1 persistence_stage1 benchmarks/persistence/stage1.md
harness/run_condition.sh enhanced run1 persistence_stage1 benchmarks/persistence/stage1.md
# inject a source change, then run stage 2 in fresh sessions
harness/run_condition.sh baseline run1 persistence_stage2 benchmarks/persistence/stage2.md
harness/run_condition.sh enhanced run1 persistence_stage2 benchmarks/persistence/stage2.md
```

### Let an agent do it

[`PROMPT.md`](PROMPT.md) is a bootstrap prompt: point a Pi agent at it and the
agent reads the repo, inspects `inputs/`, sets up baseline vs experiment with
`harness/setup_test.sh`, runs the suite, and reports. In the container:

```bash
docker/run.sh agent
```

### Setup only (bring your own repo and tool)

```bash
harness/setup_test.sh --repo inputs/repo.zip --tool inputs/tool \
  --tool-tools 'read,bash,edit,write,codeindex_*'
source work/experiment.env
harness/run_suite.sh run1 && harness/evaluate.py run1
```

## Claiming a test

Before running, reserve the `(tool × task family × repo × model)` cell by
opening a **Claim a test** issue. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the
commit-message policy (`Fix` / `Add` / `Chore`, no co-author trailers) and the
claim process.

## Verifying the tool was actually used

A tool being installed is not evidence it was used. For each enhanced run, parse
the system prompt and tool events:

```bash
python3 - <<'PY'
import json
p = "results/run1/enhanced/navigation/stdout.jsonl"
for line in open(p):
    e = json.loads(line)
    if e.get("type") == "message_start" and e["message"].get("role") == "system":
        print([n for n in e["message"]["sections"]["tools"].split("\n") if n.startswith("- codeindex")][:3])
    if e.get("type") == "tool_execution_start":
        print("CALL", e.get("toolName"))
PY
```

## Limitations

- The reference corpus behind `FINDINGS.md` is private; the public fixture is a
  neutral stand-in with the same task shape, so absolute numbers may differ.
- The scoring rubric is keyword-based and coarse; treat it as a smoke test, not
  a ground truth. Hidden tests are on the roadmap.
- Directory isolation is **not** a sandbox. Use a container or a dedicated user
  for untrusted work.
- n is small. Re-run at least 3 counterbalanced trials before trusting a delta.

## License

MIT — see [`LICENSE`](LICENSE).
