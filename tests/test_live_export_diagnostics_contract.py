from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "companion_mod/scripts/bb_agent/live_export.nut"


def test_live_export_diagnostics_are_bounded_and_deduplicated() -> None:
    text = EXPORT.read_text(encoding="utf-8")
    assert "DiagnosticMaxErrorChars = 240" in text
    assert 'split(errorText, "\\r\\n\\t").join(" ")' in text
    assert "errorText.slice(0, this.DiagnosticMaxErrorChars)" in text
    assert "LastLoggedExportDiagnostic = null" in text
    assert 'local diagnostic = _context + "|" + this.LastExportStage' in text
    assert "if (diagnostic == this.LastLoggedExportDiagnostic) return;" in text
    assert "this.LastLoggedExportDiagnostic = null;" in text


def test_stream_start_diagnostics_distinguish_export_stages() -> None:
    text = EXPORT.read_text(encoding="utf-8")
    common = text.index('this.LastExportStage = "common_envelope";')
    record = text.index('local record = this._common("STREAM_START");', common)
    canonical = text.index('this.LastExportStage = "canonical_json";')
    canonical_call = text.index("wire.canonicalJson(_record);", canonical)
    frame = text.index('this.LastExportStage = "frame_encoding";')
    frame_call = text.index("wire.encodeFrame(_record);", frame)
    emission = text.index('this.LastExportStage = "log_emission";')
    log_call = text.index("::logInfo(frame);", emission)
    assert common < record
    assert canonical < canonical_call < frame < frame_call < emission < log_call


def test_live_export_failure_log_contains_only_bounded_technical_metadata() -> None:
    text = EXPORT.read_text(encoding="utf-8")
    start = text.index("function _reportExportFailure")
    end = text.index("function _common", start)
    report = text[start:end]
    for required in (
        "_context",
        "LastExportStage",
        "errorText",
        "live_export_error context=",
        " stage=",
        " error=",
    ):
        assert required in report
    for forbidden in (
        "CurrentRaw",
        "RawSourceFingerprintInputs",
        "payload",
        "kernel_identity",
        "DEBUG_GROUND_TRUTH",
        "DEBUG_ORACLE",
        "omniscient_debug",
        "BBAGENT1",
    ):
        assert forbidden not in report


def test_live_export_diagnostics_do_not_add_execution_paths() -> None:
    text = EXPORT.read_text(encoding="utf-8")
    for forbidden in (
        "Math.rand(",
        "::Math.rand(",
        ".payForAction(",
        ".equip(",
        ".unequip(",
        ".swap(",
        ".use(",
        ".wait(",
        ".endTurn(",
        "getNavigator().travel(",
    ):
        assert forbidden not in text
