from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
DIAGNOSTICS = ROOT / "companion_mod/scripts/bb_agent/capture_diagnostics.nut"


def test_diagnostics_module_loads_immediately_after_capture_substrate() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    substrate = preload.index('::include("scripts/bb_agent/capture_substrate")')
    diagnostics = preload.index('::include("scripts/bb_agent/capture_diagnostics")')
    provenance = preload.index('::include("scripts/bb_agent/runtime_provenance")')
    assert substrate < diagnostics < provenance


def test_capture_error_diagnostics_are_bounded_single_line_and_deduplicated() -> None:
    text = DIAGNOSTICS.read_text(encoding="utf-8")
    assert "DiagnosticMaxErrorChars <- 240" in text
    assert 'split(errorText, "\\r\\n\\t").join(" ")' in text
    assert "errorText.slice(0, this.DiagnosticMaxErrorChars)" in text
    assert "local diagnostic = stage + \"|\" + loggedError;" in text
    assert "if (diagnostic != this.LastLoggedDiagnostic)" in text
    assert "this.LastLoggedDiagnostic = null;" in text
    assert '"[BB-Agent Capture] capture_error stage=" + stage' in text


def test_capture_diagnostics_preserve_fail_closed_lifecycle_and_coarse_stages() -> None:
    text = DIAGNOSTICS.read_text(encoding="utf-8")
    for stage in (
        '"readiness"',
        '"fingerprint"',
        '"signature"',
        '"raw_acquisition"',
        '"ready_commit"',
    ):
        assert stage in text
    assert 'this.invalidate("capture_error");' in text
    assert "this.State.LastError = rawError;" in text
    assert "this.State.IsReady = true;" in text
    assert 'RecordType = "DECISION_READY"' in text


def test_diagnostics_never_log_raw_or_debug_state_and_never_execute_commands() -> None:
    text = DIAGNOSTICS.read_text(encoding="utf-8")
    log_lines = [line for line in text.splitlines() if "::log" in line]
    logged = "\n".join(log_lines)

    for forbidden in (
        "CurrentRaw",
        "RawSourceFingerprintInputs",
        "DEBUG_GROUND_TRUTH",
        "DEBUG_ORACLE",
        "omniscient_debug",
        "getCurrentProperties",
        "getAllInstances",
    ):
        assert forbidden not in logged

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
