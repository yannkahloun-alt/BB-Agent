from pathlib import Path

import pytest

from bb_agent.live_ready_timing import summarize_latest_ready_timing

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
TIMING = ROOT / "companion_mod/scripts/bb_agent/runtime_live_ready_timing.nut"
NUMERIC = (
    ROOT / "companion_mod/scripts/bb_agent/runtime_player_legal_numeric_compat.nut"
)
CANONICAL = ROOT / "companion_mod/scripts/bb_agent/canonical_wire.nut"
INSTALLER = ROOT / "tools/install_live_production.ps1"
VALIDATOR = ROOT / "tools/validate_live_production.ps1"
EXTRACTOR = ROOT / "tools/extract_live_ready_timing.py"


def _log(*rows: tuple[str, str]) -> bytes:
    return "\n".join(
        f'<div class="time">{timestamp}</div><div class="text">{text}</div>'
        for timestamp, text in rows
    ).encode()


def test_timing_wrapper_loads_after_failure_latch_before_tactical_hook() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    assert 'Version = "0.2.40"' in preload
    latch = preload.index("runtime_ready_failure_latch")
    timing = preload.index("runtime_live_ready_timing")
    hook = preload.index("hooks/tactical_state")
    assert latch < timing < hook


def test_timing_wrapper_is_production_only_and_rethrows() -> None:
    text = TIMING.read_text(encoding="utf-8")
    assert "if (oracle.Enabled)" in text
    assert "originalEmitReady.acall" in text
    assert "ready_begin" in text
    assert "ready_end" in text
    assert "success=true" in text
    assert "success=false" in text
    assert '" stage=" + this.LastExportStage' in text
    assert "throw error;" in text
    assert "TimingStageObserver" in text
    assert '"[BB-Agent Live Timing] stage_" + _boundary' in text
    for forbidden in ("payload", "getAllInstances", "findPath(", "getCostForPath("):
        assert forbidden not in text


def test_timing_parser_reports_latest_complete_pair(tmp_path: Path) -> None:
    path = tmp_path / "log.html"
    path.write_bytes(
        _log(
            ("10:00:00", "[BB-Agent Live Timing] ready_begin battle=1 generation=2"),
            (
                "10:00:03",
                "[BB-Agent Live Timing] ready_end battle=1 generation=2 success=true",
            ),
            ("10:05:00", "[BB-Agent Live Timing] ready_begin battle=1 generation=3"),
            (
                "10:05:01",
                "[BB-Agent Live Timing] ready_end battle=1 generation=3 "
                "success=false stage=affordance_acquisition",
            ),
        )
    )
    assert summarize_latest_ready_timing(path) == {
        "battle_sequence": 1,
        "source_generation": 3,
        "begin_time": "10:05:00",
        "end_time": "10:05:01",
        "success": False,
        "failure_stage": "affordance_acquisition",
        "timestamp_span_seconds": 1,
        "same_timestamp_bucket": False,
        "stage_span_seconds": {},
    }


def test_timing_parser_handles_midnight_rollover(tmp_path: Path) -> None:
    path = tmp_path / "log.html"
    path.write_bytes(
        _log(
            ("23:59:59", "[BB-Agent Live Timing] ready_begin battle=4 generation=8"),
            (
                "00:00:01",
                "[BB-Agent Live Timing] ready_end battle=4 generation=8 success=true",
            ),
        )
    )
    summary = summarize_latest_ready_timing(path)
    assert summary["timestamp_span_seconds"] == 2
    assert summary["failure_stage"] is None
    assert summary["stage_span_seconds"] == {}


def test_timing_parser_reports_coarse_stage_spans(tmp_path: Path) -> None:
    path = tmp_path / "log.html"
    path.write_bytes(
        _log(
            ("10:00:00", "[BB-Agent Live Timing] ready_begin battle=1 generation=2"),
            (
                "10:00:01",
                "[BB-Agent Live Timing] stage_begin stage=player_legal_projection "
                "battle=1 generation=2",
            ),
            ("10:00:05", "unrelated timestamped log row"),
            (
                "10:00:11",
                "[BB-Agent Live Timing] stage_end stage=player_legal_projection "
                "battle=1 generation=2",
            ),
            (
                "10:00:11",
                "[BB-Agent Live Timing] stage_begin stage=affordance_acquisition "
                "battle=1 generation=2",
            ),
            (
                "10:00:14",
                "[BB-Agent Live Timing] stage_end stage=affordance_acquisition "
                "battle=1 generation=2",
            ),
            (
                "10:00:15",
                "[BB-Agent Live Timing] ready_end battle=1 generation=2 success=true",
            ),
        )
    )
    summary = summarize_latest_ready_timing(path)
    assert summary["timestamp_span_seconds"] == 15
    assert summary["stage_span_seconds"] == {
        "player_legal_projection": 10,
        "affordance_acquisition": 3,
    }


def test_timing_parser_requires_complete_pair(tmp_path: Path) -> None:
    path = tmp_path / "log.html"
    path.write_bytes(
        _log(("10:00:00", "[BB-Agent Live Timing] ready_begin battle=1 generation=2"))
    )
    with pytest.raises(ValueError, match="no complete production READY timing pair"):
        summarize_latest_ready_timing(path)


def test_extractor_fails_unsuccessful_ready_pair() -> None:
    text = EXTRACTOR.read_text(encoding="utf-8")
    assert 'if summary["success"] is not True:' in text
    assert "return 3" in text
    assert "failure_stage" in text


def test_validator_preserves_failed_ready_json_and_surfaces_stage() -> None:
    text = VALIDATOR.read_text(encoding="utf-8")
    assert "$extractExit = $LASTEXITCODE" in text
    assert "if (Test-Path -LiteralPath $Out)" in text
    assert "Get-Item -LiteralPath $Out -ErrorAction Stop" in text
    assert "companion_version -NotePropertyValue '0.2.40'" in text
    assert "$timing.failure_stage" in text
    assert "Timing JSON verified on disk:" in text
    failure = text.index("if ($extractExit -ne 0)")
    complete = text.index("PRODUCTION VALIDATION COMPLETE")
    assert failure < complete


def test_production_installer_excludes_debug_overlay() -> None:
    text = INSTALLER.read_text(encoding="utf-8")
    assert 'Version = "0\\.2\\.40"' in text
    assert "runtime_player_legal_numeric_compat" in text
    assert "runtime_live_ready_timing" in text
    assert "exactly one BB-Agent production zip" in text
    assert "zz_bb_agent_debug_oracle.zip" not in text
    assert "Copy-Item (Join-Path $RepoRoot 'companion_mod\\debug_oracle" not in text


def test_numeric_layer_loads_after_projection_hardening_before_identity() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    projection = preload.index("player_legal_projection")
    hardening = preload.index("player_legal_hardening")
    numeric = preload.index("runtime_player_legal_numeric_compat")
    identity = preload.index("canonical_identity")
    live_export = preload.index("live_export")
    assert projection < hardening < numeric < identity < live_export


def test_numeric_layer_normalizes_source_proven_whole_number_fields() -> None:
    text = NUMERIC.read_text(encoding="utf-8")
    assert "local originalOwnedResources = legal._ownedResources;" in text
    assert "local originalItemState = legal._itemState;" in text
    assert "local originalOwnedStats = legal._ownedStats;" in text
    for field in (
        "hit_points",
        "maximum_hit_points",
        "action_points",
        "maximum_action_points",
        "fatigue",
        "fatigue_capacity",
        "head_armor",
        "maximum_head_armor",
        "body_armor",
        "maximum_body_armor",
        "morale",
        "initiative",
    ):
        assert f'"{field}"' in text
    assert "equipment.condition" in text
    assert "equipment.ammunition" in text
    assert "tactical_stats." in text

    projection = (
        ROOT / "companion_mod/scripts/bb_agent/player_legal_projection.nut"
    ).read_text(encoding="utf-8")
    assert 'ammoKind == "integer" || ammoKind == "float"' in projection


def test_numeric_layer_converts_whole_float_and_rejects_fractional_float() -> None:
    text = NUMERIC.read_text(encoding="utf-8")
    float_guard = text.index('if (kind != "float") return _wrapper;')
    conversion = text.index("local integerValue = value.tointeger();", float_guard)
    fractional_guard = text.index("if (value != integerValue)", conversion)
    failure = text.index(
        'throw "player-legal whole-number field is fractional:', fractional_guard
    )
    assignment = text.index("_wrapper.value = integerValue;", failure)
    assert float_guard < conversion < fractional_guard < failure < assignment
    assert "item.condition = this._exactWholeNumber" in text


def test_canonical_wire_still_rejects_generic_floats() -> None:
    text = CANONICAL.read_text(encoding="utf-8")
    assert (
        'if (kind == "float") throw "canonical live JSON does not accept floats";'
        in text
    )
