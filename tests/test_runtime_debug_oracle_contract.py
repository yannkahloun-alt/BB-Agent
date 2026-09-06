from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
ORACLE = ROOT / "companion_mod/scripts/bb_agent/runtime_debug_oracle.nut"
PROJECTION = ROOT / "companion_mod/scripts/bb_agent/player_legal_projection.nut"
HARDENING = ROOT / "companion_mod/scripts/bb_agent/player_legal_hardening.nut"
AFFORDANCES = ROOT / "companion_mod/scripts/bb_agent/affordance_export.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_debug_oracle_is_explicit_smoke_opt_in_and_loads_last() -> None:
    preload = _text(PRELOAD)
    assert 'Version = "0.2.14"' in preload
    assert "::BBAGENT_ENABLE_DEBUG_ORACLE <- true;" in preload
    ready_latch = preload.index("scripts/bb_agent/runtime_ready_failure_latch")
    oracle = preload.index("scripts/bb_agent/runtime_debug_oracle")
    hook = preload.index("scripts/bb_agent/hooks/tactical_state")
    assert ready_latch < oracle < hook


def test_oracle_payload_exposes_native_truth_in_separate_profile() -> None:
    text = _text(ORACLE)
    required = (
        'ProfileVersion = "bb-agent-live-debug-oracle.v1"',
        'record.information_profile <- "omniscient_debug";',
        "visible_for_player = tile.IsVisibleForPlayer",
        "discovered = tile.IsDiscovered",
        "native_neighbors = neighbors",
        "hidden_to_player = placed && !_actor.isPlayerControlled()",
        "melee_defense = properties.getMeleeDefense()",
        "ranged_defense = properties.getRangedDefense()",
        "navigator.findPath(",
        "navigator.getCostForPath(",
        "prefixes = []",
        "snapshot.ap_budget <- budget;",
    )
    for token in required:
        assert token in text


def test_oracle_emits_before_player_legal_and_cannot_invalidate_capture() -> None:
    text = _text(ORACLE)
    debug_emit = text.index('record.information_profile <- "omniscient_debug";')
    legal_emit = text.index("return originalEmitReady.acall([this, _event]);")
    assert debug_emit < legal_emit
    assert "capture.invalidate(" not in text
    assert "capture.State." not in text
    assert "[BB-Agent Oracle] oracle_error" in text


def test_debug_oracle_does_not_enter_player_legal_producers() -> None:
    for path in (PROJECTION, HARDENING, AFFORDANCES):
        text = _text(path)
        assert "BBAGENT_DebugOracle" not in text
        assert "oracle_profile_version" not in text
        assert "omniscient_debug" not in text


def test_debug_oracle_is_read_only() -> None:
    text = _text(ORACLE)
    forbidden = (
        ".travel(",
        ".use(",
        ".onUse(",
        ".payForAction(",
        ".equip(",
        ".unequip(",
        ".swap(",
        ".wait(",
        ".endTurn(",
        "initNextTurnBecauseOfWait(",
        "Math.rand(",
        "::Math.rand(",
    )
    for token in forbidden:
        assert token not in text
