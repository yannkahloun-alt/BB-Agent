import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACTOR = ROOT / "tools/extract_live_ready_timing.py"
VALIDATOR = ROOT / "tools/validate_live_production.ps1"


def test_extractor_writes_diagnostic_json_when_no_complete_pair(tmp_path: Path) -> None:
    log = tmp_path / "log.html"
    out = tmp_path / "production-ready-timing.json"
    log.write_text("<html><body>no timing markers</body></html>", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(EXTRACTOR),
            "--log",
            str(log),
            "--out",
            str(out),
            "--wait-seconds",
            "0",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["success"] is None
    assert payload["diagnostic_status"] == "no_complete_ready_timing_pair"
    assert "no complete production READY timing pair" in payload["diagnostic_error"]


def test_validator_preserves_incomplete_pair_diagnostic_json() -> None:
    text = VALIDATOR.read_text(encoding="utf-8")
    assert "if ($null -ne $timing)" in text
    assert "Diagnostic JSON preserved: $Out" in text
    assert "companion_version -NotePropertyValue '0.2.38'" in text
    assert "source_commit -NotePropertyValue $head" in text
