# Docker isolation

Running a code-intelligence extension means running third-party code inside the
Pi process, with the same OS permissions as Pi. This directory does the
practical minimum to contain that: a container with **no host home, no host
credentials, a read-only root filesystem, and only `inputs/` exposed**.

## Lifecycle

```bash
docker/run.sh build      # build the image
docker/run.sh run        # prepare inputs + run + write results to out/
docker/run.sh agent      # let a Pi agent bootstrap the test from PROMPT.md
docker/run.sh shell      # poke around inside
docker/run.sh down       # remove containers + volumes (no trace)
docker/run.sh clean      # down + delete the image
```

`run` and `agent` are `--rm`, so tearing down is automatic; `down`/`clean` are
there for completeness.

## Inputs

```
inputs/
  repo.zip        # the repository to test (or inputs/repo/ unzipped)
  tool/           # the Pi extension / tool to test
```

`repo.zip` is unpacked into two identical working copies. The harness then runs
baseline (built-in tools only) against enhanced (built-in tools + the tool).

## Credentials

The container needs model access, so it needs a key. Options, in order of
preference:

1. A scoped, short-lived key passed as the provider env (no file).
2. `PI_AUTH_DIR=/path/with/auth.json docker/run.sh run` — read-only, but the
   untrusted extension can read it. Accept that tradeoff deliberately.

Nothing is persisted: `configs/`, `work/`, `results/` and `$HOME` are tmpfs.

## Limit the network

The container has egress for the model API. To restrict it, run the model behind
a local proxy and use a Compose network that reaches only the proxy. The default
`compose.yaml` intentionally does not cut networking, because the agent cannot
run without a model.
