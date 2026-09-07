from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
DISCOVERY = (
    ROOT / "companion_mod/scripts/bb_agent/runtime_combat_sandbox_discovery.nut"
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_discovery_override_loads_before_bounds_and_continuity() -> None:
    preload = _text(PRELOAD)
    base = preload.index("scripts/bb_agent/runtime_combat_sandbox")
    discovery = preload.index("scripts/bb_agent/runtime_combat_sandbox_discovery")
    bounds = preload.index("scripts/bb_agent/runtime_combat_sandbox_bounds")
    continuity = preload.index("scripts/bb_agent/runtime_combat_sandbox_continuity")
    assert base < discovery < bounds < continuity


def test_begin_only_seeds_bounded_discovery_jobs() -> None:
    text = _text(DISCOVERY)
    begin = text[text.index("sandbox.begin = function(_raw)") : text.index("sandbox._processDiscovery")]

    for token in (
        'this._enqueue("player_legal_build",',
        'this._enqueue("raw_meta",',
        'this._enqueue("discover_raw_input",',
        'this._enqueue("discover_actor",',
        'this._enqueue("discover_tile",',
    ):
        assert token in begin

    for forbidden in (
        "foreach (",
        "for (",
        "this._enqueueActors(",
        "this._enqueueTiles(",
        "getAllItems()",
        ".m.Skills",
    ):
        assert forbidden not in begin


def test_discovery_cursors_advance_one_element_at_a_time() -> None:
    text = _text(DISCOVERY)
    for token in (
        'kind == "discover_raw_input"',
        'kind == "discover_actor"',
        'kind == "discover_actor_skill"',
        'kind == "discover_actor_item"',
        'kind == "discover_tile"',
        "index + 1",
        "actor_index + 1",
        "skill_index + 1",
        "item_index + 1",
        "y + 1",
    ):
        assert token in text


def test_discovery_emits_or_queues_full_existing_record_set() -> None:
    text = _text(DISCOVERY)
    for token in (
        '"raw_fingerprint_input"',
        '"actor_core"',
        '"actor_state"',
        '"actor_properties"',
        '"actor_skills_container"',
        '"actor_items_container"',
        '"actor_ai"',
        '"actor_skill"',
        '"actor_item"',
        '"tile"',
    ):
        assert token in text


def test_discovery_delegates_normal_record_jobs_to_base_processor() -> None:
    text = _text(DISCOVERY)
    assert "local originalProcessJob = sandbox._processJob;" in text
    assert "return originalProcessJob.acall([this, _job]);" in text
    assert "sandbox._processJob = function(_job)" in text
