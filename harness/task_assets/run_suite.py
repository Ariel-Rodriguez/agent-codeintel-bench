#!/usr/bin/env python3
"""Deterministic offline full suite; traces contain actual observation decisions."""
import argparse
import importlib.util
import inspect
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
DEFAULT_VERBOSE = False


def transaction(operation_id):
    from widgets.guarded_transaction import GuardedTransaction
    tx = GuardedTransaction(operation_id)
    tx.advance("prepare")
    tx.advance("submit")
    return tx


def trace_scenarios(focus=None):
    from service.routes import observation_route
    from widgets.operation_log import OperationLog
    names = [focus] if focus else ["timestamp", "replay", "terminal"]
    for name in names:
        count = 3 if focus else 64 if name == "timestamp" else 12
        failed = False
        for i in range(count):
            with tempfile.TemporaryDirectory() as tmp:
                log = OperationLog(tmp)
                tx = transaction(f"op-{i:03}")
                if name == "timestamp":
                    seconds = 1700000000 - (i % 10) / 2
                    unit = "ms" if i % 2 else "s"
                    request = {"operation_id": tx.operation_id, "observation_id": f"obs-{i}",
                               "observed_at": seconds * (1000 if unit == "ms" else 1), "unit": unit,
                               "open": True, "state": "open"}
                    result = observation_route(request, transaction=tx, log=log, now=1700000000, stale_seconds=5)
                    good = result["outcome"] == "captured"
                    detail = {"wire": request, "decision": result, "attempts": tx.state.attempts}
                    diagnostic = "OBS_TS_UNIT_MISMATCH"
                elif name == "replay":
                    first = tx.observe("first", timestamp=1000, authorized=True)
                    result = tx.observe(f"second-{i}", timestamp=1000, authorized=True)
                    good = not result.replay and result.reason == "terminal"
                    detail = {"first": first.__dict__, "new_identity": result.__dict__, "history": tx.state.history}
                    diagnostic = "REPLAY_ID_COLLISION"
                else:
                    log.record_transition(tx.operation_id, phase="captured", observation_id="first", reason="fresh")
                    result = log.record_transition(tx.operation_id, phase="refused", observation_id=f"late-{i}", reason="terminal")
                    good = result["phase"] == "captured" and len(result["events"]) == 2
                    detail = {"durable_record": result, "expected_terminal": "captured", "expected_events": 2}
                    diagnostic = "TERMINAL_LOG_REGRESSION"
                failed |= not good
                print(f"TRACE {name} {i:03} " + json.dumps(detail, sort_keys=True))
                if i == count // 2 and failed:
                    print(f"DIAGNOSTIC {diagnostic}: scenario decisions disagree with the integration contract")
        print(f"SCENARIO {name}: {'FAIL' if failed else 'PASS'}; focused command: python3 tools/run_suite.py --focus {name}")


def suite(focus=None):
    tests = unittest.TestSuite()
    loader = unittest.TestLoader()
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[path.stem] = module
        spec.loader.exec_module(module)
        loaded = loader.loadTestsFromModule(module)
        for group in loaded:
            for test in group:
                if not focus or focus in test.id():
                    tests.addTest(test)
        for name, function in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("test_") and function.__module__ == module.__name__ and (not focus or focus in name):
                tests.addTest(unittest.FunctionTestCase(function))
    return tests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--focus", choices=("timestamp", "replay", "terminal"))
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if not args.quiet and (DEFAULT_VERBOSE or args.verbose or args.focus):
        trace_scenarios(args.focus)
    tests = suite(args.focus)
    if not tests.countTestCases():
        parser.error("no tests selected")
    result = unittest.TestResult()
    tests.run(result)
    for test, failure in result.failures + result.errors:
        print(f"FAIL {test.id()}\n{failure}")
    print(f"Ran {result.testsRun} tests; failures={len(result.failures)} errors={len(result.errors)} skipped={len(result.skipped)}")
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
