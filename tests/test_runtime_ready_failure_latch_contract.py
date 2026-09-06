from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
LATCH = ROOT / "companion_mod/scripts/bb_agent/runtime_ready_failure_latch.nut"


def test_ready_failure_latch_loads_after_runtime_compat_before_hook() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    entity_compat = preload.index(
        '::include("scripts/bb_agent/runtime_entity_fingerprint_compat")'
    )
    latch = preload.index('::include("scripts/bb_agent/runtime_ready_failure_latch")')
    hook = preload.index('::include("scripts/bb_agent/hooks/tactical_state")')
    assert entity_compat < latch < hook


def test_failed_signature_is_latched_and_same_signature_stays_quiet() -> None:
    text = LATCH.read_text(encoding="utf-8")
    assert "capture.FailedReadySignature <- null;" in text
    assert "this.FailedReadySignature = this.State.LastReadySignature;" in text
    assert "if (signature == this.FailedReadySignature)" in text
    assert "this.State.IsReady = false;" in text
    assert "this.State.CurrentRaw = null;" in text
    assert "return null;" in text
    assert "this.FailedReadySignature = null;" in text


def test_invalidation_delivery_is_one_shot_and_new_signature_can_advance() -> None:
    text = LATCH.read_text(encoding="utf-8")
    assert "if (!this.State.IsReady) return null;" in text
    assert "return this.invalidate(readiness.Reason);" in text
    assert (
        'local invalidated = this.State.IsReady ? this.invalidate("capture_error") : null;'
        in text
    )
    assert "if (!duplicate)" in text
    assert "++this.State.SourceGeneration;" in text
    assert "this.State.LastReadySignature = signature;" in text
    assert "return invalidated;" in text


def test_export_failure_latches_before_existing_invalidation_path() -> None:
    text = LATCH.read_text(encoding="utf-8")
    assert "local originalEmitReady = liveExport._emitReady;" in text
    assert "return originalEmitReady.acall([this, _event]);" in text
    assert "capture._latchCurrentReadyFailure();" in text
    assert "throw error;" in text
    assert "capture.invalidate(" not in text.split("local originalEmitReady", 1)[1]


def test_ready_failure_latch_preserves_safety_boundary() -> None:
    text = LATCH.read_text(encoding="utf-8")
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
        "DEBUG_GROUND_TRUTH",
        "DEBUG_ORACLE",
        "omniscient_debug",
    ):
        assert forbidden not in text
