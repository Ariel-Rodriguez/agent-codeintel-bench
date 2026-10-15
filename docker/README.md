# Docker isolation

A code-intelligence extension runs inside the Pi process with the same OS
permissions as Pi. Treat every extension and every target repo as untrusted.
This directory contains it.

## Network model: no direct egress

```
bench-net (internal)                 gateway                default bridge
────────────────────   bench  ──>  gateway  ──only model host──>  internet
```

- `bench` is attached **only** to `bench-net`, an internal Docker network with no
  route off the host. It cannot reach the internet directly.
- `gateway` is the single allowlisted egress path: it forwards to one
  `UPSTREAM_BASE_URL` (the model API). A malicious extension can reach the model
  and nothing else — it cannot exfiltrate to arbitrary hosts.
- `probe` runs with `network_mode: none` — **zero** network.

## Lifecycle

```bash
export UPSTREAM_BASE_URL=https://your-model-host/v1   # for `run`
docker/run.sh build      # build the image
docker/run.sh probe      # static scan + no-network load of the extension
docker/run.sh run        # prepare inputs + run through the gateway + write out/
docker/run.sh agent      # let a Pi agent bootstrap the test from PROMPT.md
docker/run.sh shell      # poke around in the bench container
docker/run.sh down       # remove containers + volumes (no trace)
docker/run.sh clean      # down + delete the image
```

`run`, `probe`, `agent` are `--rm`, so teardown is automatic.

## Malicious-extension check

```bash
# scan the tool in inputs/tool (or the demo example if absent)
docker/run.sh probe
```

This does two things:

1. **Static scan** (`harness/scan_extension.py`): flags process execution,
   filesystem writes, network access, secret-path reads, `eval`, obfuscation.
   Heuristic only — no hits is not a clean bill of health.
2. **Dynamic load** in the `probe` container: the entry runs with no network and
   a read-only root. Network and write attempts fail (`ENETUNREACH`,
   `ERR_ACCESS_DENIED`) instead of succeeding.

Try it on the bundled demo:

```bash
mkdir -p inputs && cp -R examples/untrusted-extension inputs/tool
docker/run.sh probe
```

## Tools with dependencies or downloaded models

A no-network container cannot `npm install` or fetch a model at run time. Bake
both into a per-tool image at **build** time (the build may use the network):

```bash
docker/run.sh tool /path/to/tool          # -> agent-codeintel-bench-tool:<name>
source work/tool.env
export ENHANCED_TOOLS='read,bash,edit,write,<prefix>_*'
UPSTREAM_BASE_URL=<model /v1> docker/run.sh probe   # scans/loads the baked tool
UPSTREAM_BASE_URL=<model /v1> docker/run.sh run     # offline benchmark
```

The tool directory may ship two optional hooks:

- `provision.sh` — extra build-time setup, run after dependency install.
- `warmup.sh` — download model caches; they are stored under `/opt/tool-cache`
  in the image.

At run time the caches are hydrated into a writable tmpfs and
`HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` are set, so the tool reads them
without any network. `work/tool.env` records `BENCH_IMAGE`, `TOOL_PATH`, and
`TOOL_ENTRY`; source it before `run`/`probe` so Compose uses the tool image.

## Inputs

```
inputs/
  repo.zip        # the repository to benchmark (or inputs/repo/ unzipped)
  tool/           # the Pi extension / tool to test
```

## Credentials

The container needs model access, so it needs a key. Options:

1. A scoped, short-lived key as the provider env (no file).
2. `PI_AUTH_DIR=/path/with/auth.json docker/run.sh run` — read-only, but the
   untrusted extension can read it. Accept that deliberately. The key is only
   ever used against the gateway's single upstream.

Nothing is persisted by the container itself: `configs/`, `work/`, `results/` and
`$HOME` are tmpfs. The only host-visible output is the results bind-mounted at
`out/`, which you delete when you are done.

## The isolated experiment

`docker/run.sh isolate` runs the counterbalanced experiment with **one fresh
container per condition** (see `harness/run_isolated.sh`). Each container gets
only the corpus and one task prompt, mounted read-only; `reference.json` and other
runs are never mounted. Scoring happens on the host, after the raw stream is
captured.
