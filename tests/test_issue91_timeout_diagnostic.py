# fmt: off
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACTOR = ROOT / "tools/extract_live_ready_timing.py"
VALIDATOR = ROOT / "tools/validate_live_production.ps1"
CAPTURE_DIAGNOSTICS = ROOT / "companion_mod/scripts/bb_agent/capture_diagnostics.nut"
ExtractorResult = tuple[subprocess.CompletedProcess[str], dict]


def _run_extractor(log: Path, out: Path) -> ExtractorResult:
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


def test_extractor_classifies_capture_error_before_ready(tmp_path: Path) -> None:
    log = tmp_path / "log.html"
    out = tmp_path / "production-ready-timing.json"
    log.write_text(
        '<div class="text">[BB-Agent Live Timing] loaded production_only=true '
        'wraps=DECISION_READY</div>\n'
        '<div class="text">[BB-Agent Capture] capture_error stage=fingerprint '
        'error=bad actor token; advice invalidated</div>',
        encoding="utf-8",
    )

    result, payload = _run_extractor(log, out)

    assert result.returncode == 2
    assert payload["diagnostic_status"] == "capture_error_before_ready"
    assert payload["capture_error_count"] == 1
    assert payload["latest_capture_error_stage"] == "fingerprint"
    assert payload["latest_capture_error"] == "bad actor token"


def test_extractor_classifies_readiness_block(tmp_path: Path) -> None:
    log = tmp_path / "log.html"
    out = tmp_path / "production-ready-timing.json"
    log.write_text(
        '<div class="text">[BB-Agent Live Timing] loaded production_only=true '
        'wraps=DECISION_READY</div>\n'
        '<div class="text">[BB-Agent Capture] readiness_blocked '
        'reason=input_locked</div>',
        encoding="utf-8",
    )

    result, payload = _run_extractor(log, out)

    assert result.returncode == 2
    assert payload["diagnostic_status"] == "readiness_blocked"
    assert payload["readiness_block_count"] == 1
    assert payload["latest_readiness_block_reason"] == "input_locked"


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


def test_capture_readiness_diagnostic_is_bounded_and_deduplicated() -> None:
    text = CAPTURE_DIAGNOSTICS.read_text(encoding="utf-8")
    assert "capture.LastLoggedReadinessReason <- null;" in text
    assert "readiness.Reason != this.LastLoggedReadinessReason" in text
    assert '"[BB-Agent Capture] readiness_blocked reason=" + readiness.Reason' in text
    assert "this.LastLoggedReadinessReason = null;" in text
    assert "capture.DiagnosticMaxErrorChars <- 240;" in text

    final_wrapper = (
        ROOT / "companion_mod/scripts/bb_agent/runtime_ready_failure_latch.nut"
    ).read_text(encoding="utf-8")
    assert "readiness.Reason != this.LastLoggedReadinessReason" in final_wrapper
    assert '"[BB-Agent Capture] readiness_blocked reason="' in final_wrapper


def test_validator_verifies_diagnostic_json_on_disk() -> None:
    text = VALIDATOR.read_text(encoding="utf-8")
    assert "Test-Path -LiteralPath $Out" in text
    assert "Get-Item -LiteralPath $Out -ErrorAction Stop" in text
    assert "if ($artifact.Length -le 0)" in text
    assert "PRODUCTION VALIDATION ARTIFACT:" in text
    assert "Diagnostic JSON verified on disk:" in text
    assert "companion_version -NotePropertyValue '0.2.42'" in text
    assert "source_commit -NotePropertyValue $head" in text
# fmt: on
