import subprocess
import sys


def test_print_exact_ruff_format_diff() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--diff",
            "src/bb_agent/live_ingest.py",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    raise AssertionError(result.stdout or result.stderr or "ruff produced no diff")
