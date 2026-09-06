import subprocess
import sys


def test_print_issue55_ruff_format_diff() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--diff",
            "tests/test_companion_capture_contract.py",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    raise AssertionError(result.stdout or result.stderr or "no Ruff diff produced")
