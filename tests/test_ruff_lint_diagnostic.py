import subprocess
import sys


def test_print_exact_ruff_lint_diff() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--fix",
            "--diff",
            "tests/test_companion_capture_contract.py",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    raise AssertionError(result.stdout or result.stderr or "ruff produced no diff")
