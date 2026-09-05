import subprocess
import sys


def test_emit_exact_ruff_formatting_diff() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--diff",
            "src/bb_agent/evaluator.py",
            "tests/test_evaluator.py",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    print("RUFF_DIFF_BEGIN")
    print(completed.stdout)
    print("RUFF_DIFF_END")
    raise AssertionError("temporary formatting probe")
