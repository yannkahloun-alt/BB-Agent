from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "src/bb_agent/combat_sandbox.py",
    "tests/test_issue102_movement_sandbox_contract.py",
    "tests/test_issue102_staged_combat_sandbox_contract.py",
    "tests/test_issue57_live_adapter_contract.py",
    "tests/test_movement_sandbox.py",
    "tests/test_runtime_debug_oracle_movement_compare_contract.py",
]


def test_emit_exact_ruff_format_diff() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--diff", *FILES],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError("RUFF_FORMAT_DIFF\n" + result.stdout + result.stderr)
