import subprocess
import sys


def test_emit_canonical_ruff_format_diff():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--diff",
            "src/bb_agent/features.py",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    print("RUFF_FORMAT_DIFF_BEGIN")
    print(completed.stdout)
    print("RUFF_FORMAT_DIFF_END")
    raise AssertionError("temporary formatter diff probe")
