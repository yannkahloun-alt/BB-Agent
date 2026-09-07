from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
ANCHORS = ROOT / "companion_mod/scripts/bb_agent/runtime_debug_oracle_path_anchors.nut"
EXPORT = ROOT / "companion_mod/scripts/bb_agent/live_export.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_path_anchor_oracle_loads_after_base_oracle() -> None:
    preload = _text(PRELOAD)
    base = preload.index("scripts/bb_agent/debug_oracle")
    anchors = preload.index("scripts/bb_agent/runtime_debug_oracle_path_anchors")
    compat = preload.index("scripts/bb_agent/runtime_navigator_path_compat")
    assert base < anchors < compat


def test_path_anchor_oracle_exposes_engine_supplied_tiles_only_to_diagnostics() -> None:
    anchors = _text(ANCHORS)
    for field in ("First", "SecondLastBeforeEnd", "LastBeforeEnd"):
        assert field in anchors
    assert "legal.tileID(_costs[_name])" in anchors
    assert "oracle._costSummary = function" in anchors
    assert "oracle._dumpCostFields = function" in anchors
    assert "oracle._probeNavigatorInternals = function" in anchors
    for forbidden in (
        "BBAGENT1|",
        "encodeFrame(",
        "DECISION_ORACLE",
        "record.payload",
        "information_profile",
    ):
        assert forbidden not in anchors


def test_player_legal_wire_export_remains_unchanged() -> None:
    export = _text(EXPORT)
    assert 'record.information_profile <- "player_legal"' in export
    assert "runtime_debug_oracle_path_anchors" not in export
