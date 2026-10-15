# Report 0002 — Agent-kernel (AST/BM25 + embeddings + LSP)

- **Status:** in progress
- **Tool under test:** `floydous/pi-agent-kernel` @ `b9e93be` (AST/BM25 search,
  repository map, LSP bridging; unlike report 0001 it also **redefines** the
  built-in tools, so it is a larger treatment)
- **Model:** local `Qwen3.8-27B IQ3_S, 224k context` (thinking level recorded at run)
- **Corpus:** the same private Python service as report 0001 (shape in Materials)
- **Isolation:** docker, no direct network egress; model reached only through the
  allowlisted gateway; static scan and no-network probe run before the benchmark
- **Claim:** issue [#1](https://github.com/Ariel-Rodriguez/agent-codeintel-bench/issues)

## 1. Hypothesis

- **H1:** agent-kernel improves correctness on navigation and impact analysis
  over the baseline `read, bash, edit, write` arm.
- **H0:** no improvement.
- **H2 (secondary):** it reduces input-token cost on those tasks.
- **H3 (secondary):** it is used on the repair task.
- **Falsification:** as in report 0001.

## 2. Method

Same design, tasks, counterbalancing, controls, metrics, and tool-usage
verification as [report 0001](0001-structural-code-index.html), with two changes:

1. The tool under test is agent-kernel at the pinned revision.
2. It runs inside the isolated container. The container has **no direct network
   egress**; all model traffic goes through an allowlisted gateway. Because
   agent-kernel redefines built-in tools, the baseline arm keeps the stock
   built-ins and only the enhanced arm loads agent-kernel, keeping the difference
   to "added code intelligence" as far as the tool allows.

**Pre-run checks:** `harness/scan_extension.py` (static risk scan) and
`docker/run.sh probe` (no-network load) are recorded before any benchmark run.

## 3. Materials

- Harness: this repository at the report commit; `pi 1.2.0`.
- Corpus shape: identical to report 0001 (105 files, 21,843 code lines, 91 Python
  modules, 135,063 AST nodes). See
  [`corpus-reference-complexity.json`](../data/corpus-reference-complexity.json).
- Tool dependencies and their install provenance are recorded at run time; an
  offline container cannot fetch them, so any dependency install happens before
  isolation and is logged.

## 4. Evidence

_Pending._ Populated after the counterbalanced trials. Planned table per family:
score, input/output tokens, wall time, total tool calls, tool-specific calls.

## 5. Analysis

_Pending._

## 6. Threats to validity

_Pending._ Will include: agent-kernel changes built-in tools, so the treatment is
larger than report 0001; embedding/LSP components may fail offline, which is a
prerequisite failure to be reported as `blocked`, not as a result.

## 7. Conclusion

_Pending._

## 8. Reproduction

```bash
# 1. scan the tool
python3 harness/scan_extension.py inputs/tool

# 2. no-network probe
docker/run.sh probe

# 3. isolated benchmark (model through the gateway)
UPSTREAM_BASE_URL=<model /v1> docker/run.sh run
```

## 9. Data

_Pending._
