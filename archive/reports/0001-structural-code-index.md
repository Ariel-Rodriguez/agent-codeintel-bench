# Report 0001 — Structural code-index extension

- **Status:** concluded
- **Tool under test:** `akaza21/pi-codeindex` (structural SQLite code index; per-repo)
- **Tool revision:** pinned clone; a minimal local shim was applied to convert five
  top-level union parameter schemas to object schemas for the provider. Results
  describe this patched configuration, not the published upstream release.
- **Models:** `deepseek-flash` (n=3 counterbalanced) and a local
  `Qwen3.8-27B IQ3_S, 224k context` (n=3 counterbalanced)
- **Corpus:** a private Python service, reported by shape only (see Materials)
- **Isolation:** separate agent directories per arm, project resources disabled
  (`--no-approve`), extension loaded by explicit path. Raw event streams captured.

## 1. Hypothesis

- **H1 (primary):** the extension improves **correctness** on repository
  navigation and dependency/impact analysis.
- **H2 (secondary):** the extension **reduces input-token cost** on those tasks.
- **H3 (secondary):** the extension is **used** on a bug-repair task.
- **Falsification:** H1 is falsified if baseline and enhanced scores are equal;
  H2 if the enhanced arm is not cheaper; H3 if the enhanced arm makes zero
  tool-specific calls.

## 2. Method

- **Design:** baseline (`read, bash, edit, write`) vs enhanced (same built-ins
  plus the extension's tools). The extension is the only difference.
- **Tasks:** four families — *navigation* (locate a symbol and its consumers),
  *impact* (list files affected by renaming a symbol), *repair* (fix a failing
  test from a prepared fixture), *persistence* (answer follow-up questions in a
  new session). Each family has a `reference.json` with independently derived
  answers (grep/reading, not a model).
- **Ordering:** 3 counterbalanced sequential trials for navigation and impact;
  1 trial for repair and persistence.
- **Controls:** fixed prompt (SHA-256 stored), fixed corpus commit, fixed model
  and thinking level, fixed built-in tool budget.
- **Metrics:** quality score per family, input/output tokens, wall time, total
  tool calls, and tool-specific call count.
- **Verification that the tool was used:** the system prompt sent to the model
  was parsed for tool names, and `tool_execution_start`/`_end` events were
  counted. A separate forced probe confirmed the enhanced arm calls the tool and
  the baseline cannot.

## 3. Materials

Runtime: agent `pi 1.2.0`; provider reported usage.

Corpus shape (counts only — no identifiers, paths, or semantics):

| metric | value |
|---|---|
| files | 105 |
| top-level directories | 4 |
| code / comment / blank lines | 21,843 / 957 / 3,725 (26,525 total) |
| languages | Python 91 files / 20,481 lines; YAML 13 / 1,313; TOML 1 / 49 |
| Python modules | 91 |
| classes / functions / methods | 170 / 1,392 / 547 |
| import statements | 693 |
| AST nodes / max AST depth | 135,063 / 17 |

Machine-readable: [`corpus-reference-complexity.json`](../data/corpus-reference-complexity.json).

## 4. Evidence

Scores: navigation out of 7, impact out of 5, repair out of 4, persistence out of 3.

**deepseek-flash (n=3 for navigation/impact)**

| family | arm | score (sum) | input tok (mean) | output tok (mean) | tools | wall s |
|---|---|---|---|---|---|---|
| navigation | baseline | 21/21 | 5,932 | 2,973 | 11.7 | 17.8 |
| navigation | enhanced | 20/21 | 6,483 (+9.3%) | 2,494 (−16.1%) | 12.0 | 17.4 |
| impact | baseline | 15/15 | 6,411 | 1,909 | 6.7 | 11.6 |
| impact | enhanced | 15/15 | 10,690 (+66.7%) | 1,939 | 6.3 | 13.2 |

The single non-perfect cell (navigation, enhanced, 6/7) is a **scoring artifact**:
the answer was correct but omitted one expected literal token; hand review gives
both arms 7/7.

**Qwen3.8-27B IQ3_S 224k (n=3 for navigation/impact)**

| family | arm | score (sum) | input tok (mean) | output tok (mean) | tools | wall s |
|---|---|---|---|---|---|---|
| navigation | baseline | 21/21 | 5,508 | 1,484 | 5.0 | 20.5 |
| navigation | enhanced | 21/21 | 4,476 (−18.7%) | 1,760 (+18.6%) | 6.3 | 23.7 |
| impact | baseline | 15/15 | 7,228 | 1,269 | 4.0 | 19.2 |
| impact | enhanced | 15/15 | 3,348 (−53.7%) | 1,238 | 5.0 | 18.5 |

**repair (n=1)** — both arms scored 4/4 and left the suite green (14 passed).
The enhanced arm made **0** tool-specific calls.
**persistence (n=1)** — both arms scored 3/3; the reference answers were readable
by the same OS user and one arm read them, so this cell is not clean evidence.

Raw, machine-readable: [`results-0001.json`](../data/results-0001.json).

## 5. Analysis

- **Correctness (H1):** baseline and enhanced are equal on every family under
  both models; the only difference is a scoring artifact. **Not demonstrated.**
- **Cost (H2):** model-dependent. On deepseek the enhanced arm is *more*
  expensive on input (navigation +9.3%, impact +66.7%, the latter driven by one
  23k-token run). On the local Qwen model it is *cheaper* on input, consistently
  on impact (all 3 trials negative, −3,548 / −3,265 / −4,829) and mixed on
  navigation. The saving comes from one small structural lookup replacing several
  large text dumps — so it is a property of the *interaction*, not the extension
  alone.
- **Use on repair (H3):** rejected — zero tool-specific calls.
- **Persistence:** index state was observed to go stale after a source change and
  the agent could only blindly re-sync (the agent-facing status tool exposes no
  verify option). This did not change any answer.

## 6. Threats to validity

- Small n (3 or 1 per cell); provider nondeterminism and caching dominate.
- Keyword-based scoring produced at least one false negative.
- The private corpus's reference answers were readable by the agent's OS user
  (directory isolation is not an access boundary); the persistence cell is
  contaminated.
- Repair and persistence were single trials.
- The tool was locally patched, so this measures a patched configuration.
- The two arms in the earliest trials ran concurrently, adding host noise; the
  reported counterbalanced trials ran sequentially.

## 7. Conclusion

- **H1 rejected.** No correctness benefit was demonstrated on any task family.
- **H2: model-dependent.** A reproducible input-token reduction appeared only on
  the dependency/impact task, and only with the local Qwen model.
- **H3 rejected.** The extension was not used for repair.
- **Recommendation:** do not adopt for correctness or universal cost reasons. The
  one reproducible effect does not justify a per-repo index and a stale-state
  footgun.

## 8. Reproduction

```bash
harness/prepare.sh
harness/run_suite.sh run1        # counterbalanced navigation/impact/repair
harness/evaluate.py run1
```
Corpus shape reproduces with:
```bash
harness/repo_complexity.py <private-corpus> --json
```

## 9. Data

- `docs/data/results-0001.json` — per-run scores, tokens, tools, wall time.
- `docs/data/corpus-reference-complexity.json` — corpus shape.
- Raw streams and `metrics.json` are retained privately (they contain task
  content) and are not published; the aggregate shape stands in for them.
