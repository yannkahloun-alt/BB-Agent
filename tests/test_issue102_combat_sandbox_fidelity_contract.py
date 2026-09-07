from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
FIDELITY = ROOT / "companion_mod/scripts/bb_agent/runtime_combat_sandbox_fidelity.nut"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_fidelity_layer_loads_after_discovery_before_bounds() -> None:
    preload = _text(PRELOAD)
    discovery = preload.index("scripts/bb_agent/runtime_combat_sandbox_discovery")
    fidelity = preload.index("scripts/bb_agent/runtime_combat_sandbox_fidelity")
    bounds = preload.index("scripts/bb_agent/runtime_combat_sandbox_bounds")
    assert discovery < fidelity < bounds


def test_heavy_state_is_sharded_into_independent_field_records() -> None:
    text = _text(FIDELITY)
    for token in (
        '"state_field"',
        "field_record_index",
        "owner_section",
        "owner_key",
        "field_key_kind",
        "field_key_text",
        "ordinal",
        "this._reflect(_job.target)",
        "MaxReflectEntries",
    ):
        assert token in text


def test_fidelity_shards_all_large_combat_state_families() -> None:
    text = _text(FIDELITY)
    for token in (
        'kind == "tactical_state"',
        'kind == "turn"',
        'kind == "entity_manager"',
        'kind == "tactical_global"',
        'kind == "navigator"',
        'kind == "constant"',
        'kind == "actor_state"',
        'kind == "actor_properties"',
        'kind == "actor_skills_container"',
        'kind == "actor_items_container"',
        'kind == "actor_ai"',
        'kind == "actor_skill"',
        'kind == "actor_item"',
        'kind == "tile"',
    ):
        assert token in text


def test_parent_records_describe_shards_instead_of_embedding_heavy_reflection() -> None:
    text = _text(FIDELITY)
    for token in (
        'capture_mode = "top_level_field_shards"',
        "field_count",
        "truncated",
        'field_section = "state_field"',
        "this._emitRecord(raw, _job.section, _job.key, parent)",
    ):
        assert token in text


def test_skill_item_and_tile_core_records_keep_nonstate_semantics() -> None:
    text = _text(FIDELITY)
    for token in (
        "function _skillCoreRecord(_skill)",
        "function _itemCoreRecord(_item)",
        "this._skillCoreRecord(_job.target)",
        "this._itemCoreRecord(_job.target)",
        "function _tileCorePayload(_tile)",
        "neighbor_ids = neighbors",
        "occupant = occupant",
        "properties_sharded = true",
    ):
        assert token in text
    assert "this._skillRecord(_job.target)" not in text
    assert "this._itemRecord(_job.target)" not in text


def test_fidelity_wraps_current_discovery_processor_and_begin() -> None:
    text = _text(FIDELITY)
    assert "local originalProcessJob = sandbox._processJob;" in text
    assert "return originalProcessJob.acall([this, _job]);" in text
    assert "local originalBegin = sandbox.begin;" in text
    assert "originalBegin.acall([this, _raw]);" in text
