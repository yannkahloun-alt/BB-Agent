import base64
import subprocess
import sys
from pathlib import Path


def test_emit_canonical_ruff_format(tmp_path):
    source = Path("src/bb_agent/features.py")
    target = tmp_path / "features.py"
    target.write_bytes(source.read_bytes())
    completed = subprocess.run(
        [sys.executable, "-m", "ruff", "format", str(target)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = base64.b64encode(target.read_bytes()).decode("ascii")
    print("RUFF_FORMATTED_BASE64_BEGIN")
    print(payload)
    print("RUFF_FORMATTED_BASE64_END")
    raise AssertionError("temporary formatter probe")
