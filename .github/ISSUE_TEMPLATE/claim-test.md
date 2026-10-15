---
name: Claim a test
about: Reserve one (tool revision x task family x repo x model) cell before running it
title: "[claim] <tool> — <task family> on <repo>"
labels: claim
---

## Claim

- **Tool under test (name + pinned revision):**
- **Task family:** navigation / impact / repair / persistence
- **Repo or fixture:**
- **Model / provider / thinking level:**
- **Isolation:** docker (default) / local
- **Claim expiry:** 14 days from today

## Plan

How you will run it (commands or `docker/run.sh` invocation), and what counts as
evidence.

## Result (fill in when done)

- **Run directory / commit:**
- **Quality:** per-task scores, baseline vs enhanced
- **Speed:** input/output tokens, wall time, tool calls
- **Was the tool actually used?** (system-prompt + `tool_execution_*` evidence)
- **Verdict:**
