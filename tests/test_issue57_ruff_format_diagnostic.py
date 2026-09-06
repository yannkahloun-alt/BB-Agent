from __future__ import annotations

import subprocess
import sys


def test_print_issue57_ruff_format_diff() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--diff",
            "tests/test_issue57_live_adapter_contract.py",
            "tests/test_live_canonical.py",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    raise AssertionError(result.stdout or result.stderr or "ruff produced no diff")
