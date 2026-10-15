# Per-tool image: bakes the tool's dependencies and any model cache at build
# time (when the network is available), so the benchmark itself can run offline.
#
# Build via docker/build_tool_image.sh, not directly.
ARG BASE_IMAGE=agent-codeintel-bench
FROM ${BASE_IMAGE}

USER root
ARG TOOL_NAME=tool

# The tool source is staged into the build context under tool/<name>.
COPY tool/${TOOL_NAME} /opt/tools/${TOOL_NAME}

# Install dependencies and let the tool warm its caches. Network is available
# here on purpose; the run-time container has none.
RUN set -eux; \
    cd "/opt/tools/${TOOL_NAME}"; \
    if [ -f package.json ]; then \
      if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; \
      else npm install --no-audit --no-fund; fi; \
    fi; \
    if [ -f provision.sh ]; then bash provision.sh; fi; \
    mkdir -p /opt/tool-cache/hf /opt/tool-cache/pi-cache; \
    if [ -f warmup.sh ]; then HF_HOME=/opt/tool-cache/hf TRANSFORMERS_CACHE=/opt/tool-cache/hf bash warmup.sh; fi; \
    if [ -d /home/runner/.pi/cache ]; then cp -R /home/runner/.pi/cache/. /opt/tool-cache/pi-cache/; fi; \
    chown -R runner:runner "/opt/tools/${TOOL_NAME}" /opt/tool-cache

# At run time, caches are hydrated into a writable tmpfs and the network is off.
ENV TOOL_PATH=/opt/tools/${TOOL_NAME} \
    TOOL_CACHE=/opt/tool-cache \
    HF_HOME=/home/runner/.cache/huggingface \
    TRANSFORMERS_CACHE=/home/runner/.cache/huggingface \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

USER runner
