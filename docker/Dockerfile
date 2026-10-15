# Isolated runner for untrusted code-intelligence extensions.
#
# Build:  docker/run.sh build
# Run:    docker/run.sh run
# Shell:  docker/run.sh shell
# Down:   docker/run.sh down
#
# A code-intelligence extension runs inside the Pi process with the same OS
# permissions as Pi. Treat every extension and every target repo as untrusted:
# this image gives it no host home, no host credentials, and a writable tmpfs
# only for the working copies and results.
FROM node:22-bookworm-slim

ARG PI_PACKAGE=@earendil-works/pi-coding-agent
ARG PI_VERSION=1.2.0

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates git python3 python3-venv python3-pip ripgrep unzip \
 && rm -rf /var/lib/apt/lists/*

RUN npm install -g "${PI_PACKAGE}@${PI_VERSION}"

RUN useradd --create-home --uid 10001 runner
WORKDIR /bench
COPY --chown=runner:runner . /bench
RUN chmod +x /bench/harness/*.sh /bench/harness/evaluate.py /bench/docker/entrypoint.sh

USER runner
ENV PI_SKIP_VERSION_CHECK=1 \
    PI_TELEMETRY=0 \
    PI_USER_AGENT_DIR=/auth \
    RUN_ID=run1

ENTRYPOINT ["/bench/docker/entrypoint.sh"]
CMD ["run"]
