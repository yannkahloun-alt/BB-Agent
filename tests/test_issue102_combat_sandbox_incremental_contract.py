from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
INCREMENTAL = (
    ROOT / "companion_mod/scripts/bb_agent/runtime_combat_sandbox_incremental.nut"
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_incremental_override_loads_after_full_sandbox_before_live_export() -> None:
    preload = _text(PRELOAD)
    base = preload.index("scripts/bb_agent/runtime_combat_sandbox")
    incremental = preload.index("scripts/bb_agent/runtime_combat_sandbox_incremental")
    export = preload.index("scripts/bb_agent/live_export")
    assert base < incremental < export


def test_capture_schedules_real_time_batches_and_returns_without_dump_loop() -> None:
    text = _text(INCREMENTAL)
    for token in (
        "BatchDelayMs <- 8;",
        "BatchRecordsPerTick <- 1;",
        "::Time.scheduleEvent(",
        "::TimeUnit.Real",
        "sandbox._runBatch.bindenv(sandbox)",
        "sandbox._buildJob <- function(_raw, _projection)",
        "sandbox.capture = function(_raw, _projection)",
    ):
        assert token in text

    capture = text[
        text.index("sandbox.capture = function") : text.index(
            "::logInfo(\"[BB-Agent Combat Sandbox] incremental_override_loaded"
        )
    ]
    assert "while (" not in capture
    assert "foreach (" not in capture
    assert "_emitRecord(" not in capture
    assert "::TimeUnit.Virtual" not in text


def test_incremental_job_splits_heavy_state_into_many_small_records() -> None:
    text = _text(INCREMENTAL)
    for token in (
        'kind = "tile"',
        'kind = "actor_core"',
        'kind = "actor_state"',
        'kind = "actor_current_properties"',
        'kind = "actor_base_properties"',
        'kind = "actor_skill"',
        'kind = "actor_item"',
        'kind = "actor_ai"',
        'kind = "player_legal_tile"',
        'kind = "player_legal_actor"',
        'kind = "raw_input_batch"',
        'kind = "observation_memory_entry"',
        'kind = "tactical_state_field"',
        'kind = "turn_state_field"',
        'kind = "entity_manager_field"',
    ):
        assert token in text


def test_manifest_is_committed_only_after_live_source_revalidation() -> None:
    text = _text(INCREMENTAL)
    for token in (
        "capture._fingerprintInputs(",
        "wire.canonicalHash(currentInputs)",
        "job.initial_fingerprint",
        'reason=source_changed',
        '"manifest"',
        '"root"',
        "job.expected_records",
    ):
        assert token in text

    verify = text.index("wire.canonicalHash(currentInputs)")
    manifest = text.index('"manifest"', verify)
    assert verify < manifest


def test_affordance_failure_does_not_cancel_scheduled_forensic_job() -> None:
    text = _text(INCREMENTAL)
    assert "capture.getCurrentRawAcquisition()" not in text
    assert "job.raw" in text
    assert "job.projection" in text
    assert "sandbox.ActiveJob" in text
