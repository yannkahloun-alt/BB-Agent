import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACTOR = ROOT / "tools/extract_live_ready_timing.py"
VALIDATOR = ROOT / "tools/validate_live_production.ps1"


def _run_extractor(log: Path, out: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
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
    return result, json.loads(out.read_text(encoding="utf-8"))


def test_extractor_classifies_log_without_bb_agent_entries(tmp_path: Path) -> None:
    log = tmp_path / "log.html"
    out = tmp_path / "production-ready-timing.json"
    log.write_text("<html><body>no timing markers</body></html>", encoding="utf-8")

    result, payload = _run_extractor(log, out)

    assert result.returncode == 2
    assert payload["success"] is None
    assert payload["diagnostic_status"] == "no_bb_agent_log_entries"
    assert payload["log_found"] is True
    assert payload["bb_agent_log_present"] is False
    assert payload["ready_begin_count"] == 0
    assert payload["ready_end_count"] == 0


def test_extractor_classifies_loaded_timing_without_ready_begin(tmp_path: Path) -> None:
    log = tmp_path / "log.html"
    out = tmp_path / "production-ready-timing.json"
    log.write_text(
        '<div class="text">[BB-Agent Live Timing] loaded production_only=true '
        'wraps=DECISION_READY</div>',
        encoding="utf-8",
    )

    result, payload = _run_extractor(log, out)

    assert result.returncode == 2
    assert payload["diagnostic_status"] == "ready_never_began"
    assert payload["timing_layer_loaded"] is True
    assert payload["ready_begin_count"] == 0


def test_extractor_classifies_ready_begin_without_end(tmp_path: Path) -> None:
    log = tmp_path / "log.html"
    out = tmp_path / "production-ready-timing.json"
    log.write_text(
        '<div class="text">[BB-Agent Live Timing] loaded production_only=true '
        'wraps=DECISION_READY</div>\n'
        '<div class="time">10:00:00</div><div class="text">'
        '[BB-Agent Live Timing] ready_begin battle=1 generation=0</div>',
        encoding="utf-8",
    )

    result, payload = _run_extractor(log, out)

    assert result.returncode == 2
    assert payload["diagnostic_status"] == "ready_began_without_end"
    assert payload["ready_begin_count"] == 1
    assert payload["ready_end_count"] == 0


def test_validator_preserves_incomplete_pair_diagnostic_json() -> None:
    text = VALIDATOR.read_text(encoding="utf-8")
    assert "if ($null -ne $timing)" in text
    assert "Diagnostic JSON preserved: $Out" in text
    assert "companion_version -NotePropertyValue '0.2.38'" in text
    assert "source_commit -NotePropertyValue $head" in text
