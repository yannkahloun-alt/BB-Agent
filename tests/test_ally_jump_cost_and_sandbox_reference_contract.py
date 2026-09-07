from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = ROOT / "companion_mod/scripts/bb_agent"
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
JUMP = SCRIPT_ROOT / "runtime_movement_ally_jump_cost_compat.nut"
REFS = SCRIPT_ROOT / "runtime_combat_sandbox_reference_fields.nut"


def test_ally_jump_cost_layer_loads_after_graph_before_blocking() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    graph = preload.index("scripts/bb_agent/runtime_movement_graph_compat")
    jump = preload.index("scripts/bb_agent/runtime_movement_ally_jump_cost_compat")
    blocking = preload.index("scripts/bb_agent/runtime_movement_blocking_compat")
    assert graph < jump < blocking


def test_ally_jump_cost_is_sum_of_two_constituent_steps() -> None:
    text = JUMP.read_text(encoding="utf-8")
    for required in (
        "ALLY_JUMP",
        "_movementStepCosts(",
        "ap = first.ap + second.ap",
        "path_fatigue = first.path_fatigue + second.path_fatigue",
        "execution_fatigue = first.execution_fatigue + second.execution_fatigue",
        "transition.resource_cost_resolved = true;",
    ):
        assert required in text
    assert "findPath(" not in text
    assert "getCostForPath(" not in text


def test_reference_field_layer_replaces_duplicate_runtime_graphs() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    fidelity = preload.index("scripts/bb_agent/runtime_combat_sandbox_fidelity")
    refs = preload.index("scripts/bb_agent/runtime_combat_sandbox_reference_fields")
    oracle_first = preload.index("scripts/bb_agent/runtime_combat_sandbox_oracle_first")
    assert fidelity < refs < oracle_first

    text = REFS.read_text(encoding="utf-8")
    for required in (
        "actor_skills_container",
        "Skills",
        "actor_skill",
        "actor_items_container",
        "Items",
        "actor_item",
        "entity_manager_state",
        "Instances",
        "entity_manager_instances",
        "turn_sequence_state",
        "CurrentEntities",
        "AllEntities",
        "actor_runtime_ids",
        "tactical_state",
        "Factions",
        "entity_manager_alias",
        "TacticalScreen",
        "MenuStack",
        "__bb_runtime_scaffolding",
        "originalEnqueueStateField.acall",
    ):
        assert required in text
