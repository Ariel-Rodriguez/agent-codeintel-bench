# Review — astra (openai/gpt-6-astra, medium)

- Date: 2026-10-15
- Scope: repository review (P1/P2) + next-experiment plan, read-only
- Follows the report format in [../format.md](../format.md); it is a review, not a report.

---


## 1. Prioritised findings

### P1 — fix before the next experiment

| Problem / location | Why it matters | Smallest fix |
|---|---|---|
| **The agent can read the answers and other runs.** `docker/Dockerfile` copies `benchmarks/*/reference.json` into `/bench`; `docker/compose.yaml` exposes shared `/bench/out`; both arms run as the same UID. | Directory separation is not isolation. An agent can read the rubric, other arm’s answers, or alter evidence. This repeats the contamination admitted in report 0001. | Run each condition in a fresh container containing only that task’s prompt and corpus. Keep references and prior results outside the agent container; collect and score externally. |
| **Private-repo setup still runs widget-service tasks.** `harness/run_suite.sh` hardcodes `benchmarks/`; `harness/evaluate.py` hardcodes the same references. | `--repo` changes the corpus, not the questions or scoring. A private-repo run can produce meaningless scores. | Add explicit prompt/reference roots; mount only private prompts into the runner. Keep private references host-side. |
| **Local-model configuration is silently replaced.** `docker/compose.yaml` passes `PI_PROVIDER`/`PI_MODEL`, but `harness/setup_test.sh` uses `EXP_MODEL`, defaulting to DeepSeek; `docker/entrypoint.sh` then sources the generated defaults. Gateway rewriting only works for an existing matching provider in `models.json`. | The documented local-model run can select the wrong provider or bypass the intended gateway configuration. | Use one model configuration contract; generate/validate the custom provider with gateway `baseUrl`; fail if it is absent. |
| **Baked tool selection is broken.** `docker/entrypoint.sh` prefers `/inputs/tool` over the baked tool. `docker/build_tool_image.sh` emits `TOOL_ENTRY`, but Compose/setup do not consume it. Setup independently guesses entry paths and overwrites `CODEINTEL_EXT`. | You can run the uninstalled host source instead of the dependency-complete image, load the wrong entry, or run “enhanced” without the tool. | Prefer explicit baked `TOOL_ENTRY`; pass it through Compose; require that it exists. No silent fallback. |
| **The probe does not test the actual extension.** `docker/entrypoint.sh::probe` runs the first JS file found, potentially inside `node_modules`, rather than loading the declared Pi entry. TypeScript-only tools are skipped successfully. Errors are swallowed; output is truncated; no caches are hydrated. | A green probe proves neither successful loading nor offline embeddings/LSP. The permission-restricted probe also differs from the real Pi process. | Load the exact entry through Pi under `network_mode: none`; exercise indexing, embeddings and applicable LSP operations; enforce timeout and nonzero failure; retain complete logs. |
| **Offline model preparation is not implemented automatically.** `docker/Dockerfile.tool` only downloads anything if a supplied `warmup.sh` does it. Generic HF environment variables do not establish the installed Transformers.js version’s actual cache/offline behavior. `entrypoint.sh` suppresses cache-copy failures; home is only 64/128 MB. | Missing, misplaced or partially copied embedding weights can cause downloads, failure or silent degraded treatment. | Warm the exact model/revision/dtype through the tool’s actual embedding path; configure its actual cache and local-only behavior. Size storage from measured cache bytes; make hydration failure fatal. Verify a real offline embedding. |
| **Gateway configuration is internally inconsistent.** `docker/compose.yaml` gives the gateway only the internal network, contrary to `docker/README.md` and `docker/gateway.py`. `gateway.py` concatenates upstream and request paths: documented upstream `/v1` plus runner `/v1/...` becomes `/v1/v1/...`. It also follows redirects and accepts arbitrary paths/methods. | The advertised external/local-host endpoint may be unreachable; valid requests can 404. A future bridge attachment would make the “one upstream” guarantee weaker than claimed. | For this experiment put the local inference server on the same internal network, with no other network. Configure upstream as its **origin**, without `/v1`. Restrict API paths/methods, disable redirects and environment proxies. |
| **Failures and invalid repairs can look successful.** `run_condition.sh` records Pi’s exit status but exits successfully; setup merely warns on failed pip install; `evaluate.py` still scores failures and awards repair points for the word “passed.” Missing streams can instead crash on missing `final_text`. | Prerequisite failure becomes a benchmark datum, or an unverified assertion becomes a passing repair. | Propagate failures; require complete event streams and successful treatment activation. Run trusted tests independently and reject test modifications. Fail closed on missing evidence. |
| **Task state is uncontrolled.** `run_suite.sh` never applies `benchmarks/repair/bug.patch`, never resets worktrees/caches between host-side trials, and never runs persistence. | Repair may start green or already repaired; warm indexes leak between trials; four-family claims are unsupported. | Fresh condition containers; verify identical failing repair snapshots before execution; explicitly implement persistence sessions and the between-session mutation. Predeclare cold versus warm indexing. |

### P2 — should fix

- **Scoring is permissive and sometimes contradictory:** `benchmarks/impact/reference.json` says no Python file outside `widgets` refers to the symbol while listing tests outside it. Its substring rules accept incorrect assertions containing “outside the widgets package.” Navigation does not penalise extra false paths. Use explicit set comparison and independently adjudicated semantic checks.
- **Reproducibility gaps:** `docker/Dockerfile` has a mutable base tag; `Dockerfile.tool` permits unlocked `npm install`; `setup_test.sh` can copy existing Git history/hooks and retain old configs. Pin image/dependency/model digests, export a clean corpus snapshot, clear configs, and record exact treatment patches.
- **Evidence capture is insufficient:** `run_condition.sh` captures `git diff`, not new untracked files, and does not capture the advertised system-prompt/tool-schema verification. Add an artifact manifest, complete changed-file capture, and explicit tool-registration/implementation evidence—important because agent-kernel replaces built-ins.
- **Gateway timing is distorted:** `docker/gateway.py` buffers the entire upstream response before returning it. Stream responses if latency is measured; impose request/body limits.
- **Scanner/shape limitations:** `scan_extension.py` scans zero files when given a single file and skips dependencies; `repo_complexity.py` silently ignores Python syntax failures, counts methods inside “functions,” and can count `"."` as a top-level directory. Report these definitions and failures explicitly.
- **Documentation drift:** `docs/index.md` calls 0002 “in progress” while its report says blocked; `examples/untrusted-extension/README.md` names nonexistent `scan_extension.sh`. “Nothing is persisted” in `docker/README.md` contradicts the host `out/` mount. Writable tmpfs means filesystem writes are not universally blocked.

## 2. Next experiment: execution plan and commands

**Do not use `docker/run.sh run` unchanged.** It currently cannot deliver the requested valid private-repo experiment. The commands below are a preparation/run checklist **after the P1 fixes**, not a claim that the present scripts work.

Also: the repository does not contain agent-kernel v0.4.0’s source or its embedding configuration. An exact model ID, revision, warmup invocation and tool list cannot honestly be inferred here. Report 0002’s `b9e93be` is not evidence that this is v0.4.0.

### A. Online preparation, without private data or credentials

Use a separate preparation directory; do not run tool lifecycle scripts on the host.

```bash
set -euo pipefail
export PREP="$(mktemp -d)"
mkdir -p "$PREP/evidence"

git clone https://github.com/floydous/pi-agent-kernel.git "$PREP/agent-kernel"
git -C "$PREP/agent-kernel" checkout --detach v0.4.0
git -C "$PREP/agent-kernel" rev-parse HEAD \
  | tee "$PREP/evidence/tool.commit"

python3 - "$PREP/agent-kernel/package.json" <<'PY'
import json, sys
p = json.load(open(sys.argv[1]))
assert p["version"] == "0.4.0", p["version"]
print(json.dumps(p, indent=2))
PY

python3 harness/scan_extension.py "$PREP/agent-kernel" --json \
  > "$PREP/evidence/static-scan.json"

rg -n 'transformers|pipeline|feature-extraction|cacheDir|allowRemoteModels|allowLocalModels|onnx|registerTool|language.server' \
  "$PREP/agent-kernel" > "$PREP/evidence/adapter-inspection.txt"
```

Before building, establish from that source:

- Actual `pi.extensions` entries and registered/replaced tool names.
- Exact embedding model, immutable revision, dtype and cache path.
- How to force **local-only** model resolution in the installed Transformers.js version.
- Python language-server binaries/configuration required for the claimed treatment.

Supply reviewed `provision.sh`/`warmup.sh` hooks in the staging copy. Warmup must call the **same embedding implementation** used at runtime and verify a finite, nonempty vector—not merely download an arbitrary HF model. Record hooks as provisioning changes; record any source patch separately.

Bake Python test dependencies and language servers while online too. Runtime setup must use a wheelhouse with `--no-index`, or a preinstalled environment; it must not attempt ordinary pip installation.

```bash
docker/run.sh build 2>&1 | tee "$PREP/evidence/base-build.log"

docker/run.sh tool "$PREP/agent-kernel" agent-kernel-v0.4.0 \
  2>&1 | tee "$PREP/evidence/tool-build.log"

source work/tool.env
docker image inspect "$BENCH_IMAGE" \
  > "$PREP/evidence/tool-image.json"

docker run --rm --network none --entrypoint bash "$BENCH_IMAGE" -lc \
  'cd "$TOOL_PATH"; npm ls --all; du -sk /opt/tool-cache'
```

**Gate:** no unresolved dependencies; warmed cache fits runtime storage; image and model checksums recorded. Build hooks receive neither the private repository nor model-provider credentials.

### B. Zero-egress local inference topology

Use a **preloaded local model container**, not a cloud endpoint or a host service that can itself forward requests externally. It must have only the internal benchmark network. The server must bind its container interface, not just loopback.

After starting the gateway:

```bash
export UPSTREAM_BASE_URL=http://local-model:8000   # no /v1 suffix
docker compose -f docker/compose.yaml up -d --no-build gateway

GW="$(docker compose -f docker/compose.yaml ps -q gateway)"
NET="$(docker inspect "$GW" \
  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}')"

# LOCAL_MODEL_CONTAINER must already contain the loaded model and have
# no other attached network; 8000 is its actual inference port.
docker network connect --alias local-model "$NET" "$LOCAL_MODEL_CONTAINER"

docker network inspect "$NET" > "$PREP/evidence/network.json"
docker inspect "$GW" "$LOCAL_MODEL_CONTAINER" \
  > "$PREP/evidence/runtime-containers.json"
```

Assert `Internal: true`, and assert that gateway, runner and inference server have **no other networks**. Do not “fix” connectivity by adding a normal bridge.

Create a minimal local-only `models.json` with the actual served model ID and `baseUrl: http://gateway:8080/v1`; no real cloud credentials. Verify the resulting generated configs still select that provider/model.

### C. Probe and offline acceptance gates

After correcting entry selection, cache hydration and probe semantics:

```bash
source work/tool.env
docker/run.sh probe 2>&1 | tee "$PREP/evidence/no-network-probe.log"
```

Require captured evidence of:

1. Exact v0.4.0 entry loaded, dependency versions and tool registration.
2. Successful Python-repository indexing and an actual embedding computation under `network_mode: none`.
3. LSP operation, if claimed; otherwise explicitly declare it unavailable.
4. No remote-model fallback or download attempts.
5. Separate runtime-network tests: local inference succeeds; external DNS/TCP/HTTPS and host-service access fail. Probe network isolation alone does **not** establish the benchmark network’s properties.

### D. Private tasks and measured runs

- Export the private repo at a fixed commit, excluding credentials, `.git`, hooks, environments and answer files.
- Derive private prompts/references independently. Never mount references into the agent container.
- Start with navigation and impact; add repair/persistence only after their controls exist.
- Use fresh condition containers; retain state only within a declared persistence sequence.
- Use four trials for equal order counts, not three. Verify the rewritten runner consumes the private prompts and selects the configured local model before measurement.

Once those runner fixes are implemented:

```bash
for r in run1 run2 run3 run4; do
  RUN_ID="$r" docker/run.sh run
done
```

Do **not** apply the current `harness/evaluate.py` widget references to these outputs. Score externally against the private references.

**Capture privately:** harness/tool commits, provisioning patches, image digest, lockfiles, model hashes/server flags, corpus snapshot hash and aggregate shape, prompt/reference hashes, order, effective model config, network inspections, probe logs, complete streams/stderr/statuses, tool-registration and execution evidence, index/cache state, independent test results and complete changed files. Publish only reviewed aggregates; raw prompts, streams and patches can expose the private repository.

## 3. What makes report 0001 untrustworthy

`docs/reports/0001-structural-code-index.md` has these specific limitations:

- **Known answer leakage:** persistence is contaminated, not merely noisy. Because references were readable by the same OS user, other cells need an access audit before being treated as clean.
- **No independently auditable provenance:** no exact tool SHA, shim patch, corpus hash, prompt hashes, inference-model digest or full runtime configuration is published. `docs/data/results-0001.json` contains summaries, not evidence sufficient to verify execution or correctness. Corpus shape cannot substitute for raw evidence.
- **Reproduction does not reproduce the report:** the listed `prepare.sh`/`run_suite.sh` commands default to the public fixture, do not configure the extension, do not apply the repair patch, and omit persistence.
- **Treatment-use claim is not universal:** `docs/data/results-0001.json` records **zero tool-specific calls for DeepSeek `exp6` enhanced impact**, as well as repair. Separate “extension available” from “extension used”; do not silently discard non-use runs.
- **Correctness claims exceed the evidence:** tiny samples with ceiling scores cannot establish no benefit. “H1 rejected” should be “no benefit demonstrated on these tasks.” The hand-corrected navigation score needs a documented, consistently applied adjudication.
- **Repair success is not supported by the public scorer:** saying “passed” earns the test points. Independent before/after test logs and a reviewed patch are necessary to substantiate “14 passed.”
- **Token savings are conditional:** cache accounting, cold/warm indexing, setup cost and repeated-state policy are not sufficiently documented. The data support observed input-token differences in those runs—not general cost savings.
- **Current harness defects do not prove historical runs were invalid**, but undocumented manual fixes cannot be assumed. The private evidence must establish which defects were avoided and how.
