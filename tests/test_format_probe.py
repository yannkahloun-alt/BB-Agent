import base64
import subprocess
import sys
from pathlib import Path


def test_emit_exact_ruff_formatting() -> None:
    paths = [
        Path("src/bb_agent/evaluator.py"),
        Path("tests/test_evaluator.py"),
    ]
    subprocess.run(
        [sys.executable, "-m", "ruff", "format", *(str(path) for path in paths)],
        check=True,
    )
    for path in paths:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        print(f"RUFF_FORMAT_BEGIN:{path}")
        print(encoded)
        print(f"RUFF_FORMAT_END:{path}")
    raise AssertionError("temporary formatting probe")
