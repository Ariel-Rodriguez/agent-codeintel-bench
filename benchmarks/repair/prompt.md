Bug investigation and repair task. The test suite in this repository is failing.
One test in `tests/test_freshness.py` reports a regression in
`is_observation_fresh` in `src/widgets/freshness.py`.

Find the root cause, apply the smallest correct repair, and run:

    .venv/bin/python -m pytest -q tests/test_freshness.py

Report the file and function you changed and the test result. Do not change the
tests to make them pass.
