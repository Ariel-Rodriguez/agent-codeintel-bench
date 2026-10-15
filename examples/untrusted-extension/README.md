# Untrusted extension demo

A deliberately risky file used to test two things:

1. `harness/scan_extension.py` flags its capabilities.
2. `docker/run.sh probe` runs it with **no network** and a read-only root, so the
   network and filesystem-write attempts fail instead of succeeding.

It is not a Pi extension and does nothing useful. Never load it outside the
probe container.
