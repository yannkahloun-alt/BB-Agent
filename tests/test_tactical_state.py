from dataclasses import replace

import pytest

from bb_agent.tactical_state import (
    ActionAffordance,
    ActionAffordanceSet,
    ActionKind,
    AffordanceCompleteness,
    AffordanceProvenance,
    BattleContext,
    Combatant,
    DecisionContext,
    Environment,
    HexCoord,
    InformationProfile,
    KnowledgeClass,
    KnownValue,
    LastSeen,
    LifeState,
    ObservationPoint,
    PlayerVisiblePreview,
    Relation,
    Representation,
    ResolutionStage,
    ResolvedCost,
    ResourceState,
    RulesetIdentity,
    TacticalState,
    Tile,
    TurnEntry,
    TurnState,
)
from bb_agent.versions import CURRENT_VERSIONS


def _resources(*, debug: bool = False) -> ResourceState:
    knowledge = (
        KnowledgeClass.DEBUG_GROUND_TRUTH if debug else KnowledgeClass.EXACT_OBSERVED
    )
    return ResourceState(
        hit_points=KnownValue.exact(60, knowledge),
        maximum_hit_points=KnownValue.exact(60, knowledge),
        action_points=KnownValue.exact(9, knowledge),
        maximum_action_points=KnownValue.exact(9, knowledge),
        fatigue=KnownValue.exact(0, knowledge),
        fatigue_capacity=KnownValue.exact(100, knowledge),
    )


def _state(
    profile: InformationProfile = InformationProfile.PLAYER_LEGAL,
    *,
    reverse: bool = False,
) -> TacticalState:
    tiles = (
        Tile(
            "origin",
            HexCoord(0, 0),
            0,
            "plain",
            ("east", None, None, None, None, None),
            "brother",
        ),
        Tile(
            "east",
            HexCoord(1, 0),
            0,
            "plain",
            (None, None, None, "origin", None, None),
            "enemy",
        ),
    )
    actors = (
        Combatant(
            "brother",
            Relation.PLAYER,
            True,
            LifeState.ALIVE,
            True,
            KnownValue.exact("origin"),
            _resources(),
            skill_ids=("skill.attack", "skill.attack"),
        ),
        Combatant(
            "enemy",
            Relation.HOSTILE,
            False,
            LifeState.ALIVE,
            True,
            KnownValue.exact("east"),
            _resources(debug=profile is InformationProfile.OMNISCIENT_DEBUG),
        ),
    )
    action = ActionAffordance(
        "attack:enemy",
        "brother",
        ActionKind.USE_SKILL,
        AffordanceProvenance.HANDCRAFTED_FIXTURE,
        "generation-1",
        skill_id="skill.attack",
        ap_cost=ResolvedCost(4, ResolutionStage.PREVIEW_RESOLVED, "fixture UI"),
        fatigue_cost=ResolvedCost(10, ResolutionStage.PREVIEW_RESOLVED, "fixture UI"),
        preview=PlayerVisiblePreview(displayed_hit_chance=67),
        debug_ground_truth={"enemy_melee_defense": 12},
    )
    values = dict(
        contract_version=CURRENT_VERSIONS.tactical_state,
        state_id="",
        raw_capture_id="capture-1",
        information_profile=profile,
        ruleset=RulesetIdentity("1.5", "catalog-sha", ("mod-b", "mod-a")),
        battle=BattleContext("battle-1", "player", "COMBAT"),
        decision=DecisionContext("brother", 1, 2, False, True, "BEFORE_ACTION"),
        turn_state=TurnState(),
        environment=Environment("DAY"),
        tiles=tuple(reversed(tiles)) if reverse else tiles,
        combatants=tuple(reversed(actors)) if reverse else actors,
        action_affordances=ActionAffordanceSet(
            "brother", "", "generation-1", AffordanceCompleteness.COMPLETE, (action,)
        ),
        annotations={"expected_best": "attack:enemy"},
    )
    return TacticalState.create(**values)


def test_player_legal_preview_does_not_require_hidden_defense() -> None:
    state = _state()
    enemy = next(actor for actor in state.combatants if actor.actor_id == "enemy")
    action = state.action_affordances.actions[0]

    assert action.preview.displayed_hit_chance == 67
    assert action.debug_ground_truth == {"enemy_melee_defense": 12}
    assert enemy.resources.morale.representation is Representation.UNKNOWN
    assert (
        "debug_ground_truth"
        not in state._identity_dict()["action_affordances"]["actions"][0]
    )  # type: ignore[index]


def test_round_trip_is_lossless_and_order_is_normalized() -> None:
    first = _state()
    reordered = _state(reverse=True)

    assert first.state_id == reordered.state_id
    assert TacticalState.from_dict(first.to_dict()) == first
    assert [tile.tile_id for tile in reordered.tiles] == ["east", "origin"]
    assert [actor.actor_id for actor in reordered.combatants] == ["brother", "enemy"]
    debug = _state(InformationProfile.OMNISCIENT_DEBUG)
    assert TacticalState.from_dict(debug.to_dict()) == debug


def test_identical_affordances_are_deduplicated() -> None:
    state = _state()
    duplicated = replace(
        state,
        state_id="",
        action_affordances=replace(
            state.action_affordances,
            actions=state.action_affordances.actions * 2,
        ),
    )

    assert len(duplicated.normalized().action_affordances.actions) == 1


def test_annotations_and_debug_oracle_do_not_affect_hash() -> None:
    state = _state()
    changed_annotations = replace(state, state_id="", annotations={"anything": [1, 2]})
    action = replace(
        state.action_affordances.actions[0], debug_ground_truth={"different": True}
    )
    changed_oracle = replace(
        state,
        state_id="",
        action_affordances=replace(state.action_affordances, actions=(action,)),
    )

    assert changed_annotations.normalized().state_id == state.state_id
    assert changed_oracle.normalized().state_id == state.state_id


def test_profile_changes_semantic_identity_for_same_raw_capture() -> None:
    legal = _state()
    debug = _state(InformationProfile.OMNISCIENT_DEBUG)

    assert legal.raw_capture_id == debug.raw_capture_id
    assert legal.state_id != debug.state_id


def test_raw_capture_linkage_does_not_change_semantic_identity() -> None:
    state = _state()
    another_capture = replace(state, state_id="", raw_capture_id="capture-2")

    assert another_capture.normalized().state_id == state.state_id


def test_player_legal_rejects_debug_knowledge() -> None:
    state = _state(InformationProfile.OMNISCIENT_DEBUG)
    leaked = replace(
        state, state_id="", information_profile=InformationProfile.PLAYER_LEGAL
    )

    with pytest.raises(ValueError, match="DEBUG_GROUND_TRUTH"):
        leaked.normalized()


def test_player_legal_rejects_debug_knowledge_outside_combatants() -> None:
    state = _state()
    debug_done = KnownValue.exact(True, KnowledgeClass.DEBUG_GROUND_TRUTH)
    turn_leak = replace(
        state,
        state_id="",
        turn_state=TurnState((TurnEntry("brother", debug_done),)),
    )
    with pytest.raises(ValueError, match="DEBUG_GROUND_TRUTH"):
        turn_leak.normalized()

    debug_tile = replace(state.tiles[0], visibility=KnowledgeClass.DEBUG_GROUND_TRUTH)
    tile_leak = replace(state, state_id="", tiles=(debug_tile, state.tiles[1]))
    with pytest.raises(ValueError, match="DEBUG_GROUND_TRUTH"):
        tile_leak.normalized()


def test_snapshot_local_references_are_validated() -> None:
    state = _state()
    bad_turn = replace(
        state,
        state_id="",
        turn_state=TurnState((TurnEntry("missing", KnownValue.exact(False)),)),
    )
    with pytest.raises(ValueError, match="turn entry references unknown actor"):
        bad_turn.normalized()

    enemy = state.combatants[1]
    bad_last_seen = replace(
        enemy,
        last_seen=LastSeen("missing", ObservationPoint(1, 1)),
    )
    with pytest.raises(ValueError, match="last_seen references unknown tile"):
        replace(
            state,
            state_id="",
            combatants=(state.combatants[0], bad_last_seen),
        ).normalized()

    bad_skill = replace(state.action_affordances.actions[0], skill_id="skill.missing")
    with pytest.raises(ValueError, match="skill_id is not possessed"):
        replace(
            state,
            state_id="",
            action_affordances=replace(
                state.action_affordances,
                actions=(bad_skill,),
            ),
        ).normalized()

    equip = replace(
        state.action_affordances.actions[0],
        action_id="equip:missing",
        kind=ActionKind.EQUIP_ITEM,
        skill_id=None,
        item_id="missing",
    )
    with pytest.raises(ValueError, match="item_id is not owned"):
        replace(
            state,
            state_id="",
            action_affordances=replace(state.action_affordances, actions=(equip,)),
        ).normalized()


def test_stale_affordance_set_is_rejected() -> None:
    state = _state()
    stale = replace(
        state,
        action_affordances=replace(
            state.action_affordances, captured_for_state_id="old-state"
        ),
    )

    with pytest.raises(ValueError, match="stale affordance"):
        stale.normalized()


def test_occupancy_and_neighbor_invariants_are_enforced() -> None:
    state = _state()
    bad_tile = replace(state.tiles[0], neighbors=(None,) * 6)
    broken = replace(state, state_id="", tiles=(bad_tile, state.tiles[1]))

    with pytest.raises(ValueError, match="symmetric"):
        broken.normalized()

    enemy = state.combatants[1]
    collision = replace(enemy, position=KnownValue.exact("origin"))
    occupied = replace(state, state_id="", combatants=(state.combatants[0], collision))
    with pytest.raises(ValueError, match="two actors|occupancy disagree"):
        occupied.normalized()


def test_axial_directions_and_distance_are_frozen() -> None:
    origin = HexCoord(0, 0)
    expected = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))

    assert (
        tuple((origin.neighbor(i).q, origin.neighbor(i).r) for i in range(6))
        == expected
    )
    assert origin.distance_to(HexCoord(3, -2)) == 3


def test_unknown_has_no_magic_payload() -> None:
    with pytest.raises(ValueError, match="UNKNOWN cannot carry"):
        KnownValue(
            Representation.UNKNOWN,
            KnowledgeClass.UNKNOWN,
            minimum=-1,
        )
