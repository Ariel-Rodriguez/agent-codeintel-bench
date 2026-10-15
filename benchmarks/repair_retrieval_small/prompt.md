A small regression causes valid widget observations to be refused when the supervisor clock is slightly ahead, even though the documented future-skew allowance should permit them. Restore the intended behavior without weakening malformed/stale observation refusal.

Start by running the complete offline suite with `python3 tools/run_suite.py`. Repair production code, run focused checks as useful, then rerun the complete suite. Do not change tests, the suite runner, or project configuration. Leave the repair in the working tree and report the checks you ran.
