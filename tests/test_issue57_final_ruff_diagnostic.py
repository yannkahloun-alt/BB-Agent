from __future__ import annotations

import subprocess
import sys


def test_print_final_issue57_ruff_diff() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--diff",
            "src/bb_agent/live_canonical.py",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    raise AssertionError(result.stdout or result.stderr or "ruff produced no diff")
