# Inputs

Drop what you want to test here. Contents are ignored by Git.

```
inputs/
  repo.zip        # the repository to benchmark (or inputs/repo/ unzipped)
  repo/           # alternative to repo.zip
  tool/           # the Pi extension or tool to test
```

- `repo.zip` — any repository with a test suite. `harness/setup_test.sh` unpacks
  it into two identical working copies.
- `tool/` — the extension or tool directory. The setup script looks for
  `src/pi/index.ts`, `index.ts`, `src/index.ts`, `dist/extension.js`, or
  `dist/index.js`. Override with `--tool <file>` if your entry point differs.
- If both are absent, the bundled `fixtures/widget-service` is used with no tool
  (baseline vs baseline).

The container mounts `inputs/` **read-only**. Nothing here is ever committed.
