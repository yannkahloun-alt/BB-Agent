from dataclasses import fields, replace

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
    EffectState,
    Environment,
    GroundEntity,
    HexCoord,
    InformationProfile,
    ItemState,
    KnowledgeClass,
    KnownValue,
    LastSeen,
    LifeState,
    ObservationPoint,
    PlayerVisiblePreview,
    Relation,
    Representation,
    ResolutionAuthority,
    ResolutionStage,
    ResolvedCost,
    ResolvedPreviewValue,
    ResourceState,
    RulesetIdentity,
    SkillState,
    TacticalStat,
    TacticalState,
    TargetKind,
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
        head_armor=KnownValue.exact(40, knowledge),
        maximum_head_armor=KnownValue.exact(50, knowledge),
        body_armor=KnownValue.exact(70, knowledge),
        maximum_body_armor=KnownValue.exact(80, knowledge),
        initiative=KnownValue.exact(105, knowledge),
    )


def _unknown_resources() -> ResourceState:
    unknown = KnownValue.unknown
    return ResourceState(
        hit_points=unknown(),
        maximum_hit_points=unknown(),
        action_points=unknown(),
        maximum_action_points=unknown(),
        fatigue=unknown(),
        fatigue_capacity=unknown(),
    )


def _state(
    profile: InformationProfile = InformationProfile.PLAYER_LEGAL,
    *,
    reverse: bool = False,
    reverse_sets: bool = False,
    source_generation: str = "generation-1",
    provenance: AffordanceProvenance = AffordanceProvenance.HANDCRAFTED_FIXTURE,
) -> TacticalState:
    set_values = ("z", "a", "z") if not reverse_sets else ("a", "z")
    distribution = ((2, 0.4), (1, 0.6))
    if reverse_sets:
        distribution = tuple(reversed(distribution))
    tiles = (
        Tile(
            "origin",
            HexCoord(0, 0),
            0,
            KnownValue.exact("plain"),
            ("east", None, None, None, None, None),
            "brother",
            dynamic_effects=KnownValue(
                Representation.SET,
                KnowledgeClass.EXACT_OBSERVED,
                candidates=set_values,
            ),
            movement_cost=KnownValue(
                Representation.DISTRIBUTION,
                KnowledgeClass.INFERRED,
                distribution=distribution,
                basis=set_values,
            ),
        ),
        Tile(
            "east",
            HexCoord(1, 0),
            0,
            KnownValue.exact("plain"),
            (None, None, None, "origin", None, None),
            "enemy",
            dynamic_effects=KnownValue(
                Representation.SET,
                KnowledgeClass.EXACT_OBSERVED,
                candidates=tuple(reversed(set_values)),
            ),
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
            skills=(
                SkillState(
                    "skill.attack",
                    KnownValue.exact(True),
                    enabled=KnownValue.exact(True),
                ),
            ),
            tactical_stats=(
                TacticalStat("melee_skill", KnownValue.exact(73)),
                TacticalStat("melee_defense", KnownValue.exact(18)),
            ),
            perks=KnownValue(
                Representation.SET,
                KnowledgeClass.EXACT_OBSERVED,
                candidates=tuple(f"perk.{value}" for value in set_values),
            ),
            traits=KnownValue(
                Representation.SET,
                KnowledgeClass.EXACT_OBSERVED,
                candidates=tuple(f"trait.{value}" for value in reversed(set_values)),
            ),
        ),
        Combatant(
            "enemy",
            Relation.HOSTILE,
            False,
            LifeState.ALIVE,
            True,
            KnownValue.exact("east"),
            (
                _resources(debug=True)
                if profile is InformationProfile.OMNISCIENT_DEBUG
                else _unknown_resources()
            ),
        ),
    )
    action = ActionAffordance(
        "attack:enemy",
        "brother",
        ActionKind.USE_SKILL,
        provenance,
        source_generation,
        skill_id="skill.attack",
        target_kind=TargetKind.ACTOR,
        target_actor_id="enemy",
        ap_cost=ResolvedCost(
            4,
            ResolutionStage.PREVIEW_RESOLVED,
            ResolutionAuthority.HANDCRAFTED_FIXTURE,
        ),
        fatigue_cost=ResolvedCost(
            10,
            ResolutionStage.PREVIEW_RESOLVED,
            ResolutionAuthority.HANDCRAFTED_FIXTURE,
        ),
        preview=PlayerVisiblePreview(
            displayed_hit_chance=ResolvedPreviewValue(
                67, ResolutionStage.PREVIEW_RESOLVED, ResolutionAuthority.PLAYER_UI
            ),
            affected_tile_ids=ResolvedPreviewValue(
                ["east"],
                ResolutionStage.PREVIEW_RESOLVED,
                ResolutionAuthority.PLAYER_UI,
            ),
        ),
        debug_ground_truth=(
            {"enemy_melee_defense": 12}
            if profile is InformationProfile.OMNISCIENT_DEBUG
            else None
        ),
    )
    values = dict(
        contract_version=CURRENT_VERSIONS.tactical_state,
        state_id="",
        raw_capture_id="capture-1",
        information_profile=profile,
        ruleset=RulesetIdentity("1.5", "catalog-sha", ("mod-b", "mod-a")),
        battle=BattleContext(
            "battle-1",
            "player",
            "COMBAT",
            hostile_faction_ids=set_values,
            allied_faction_ids=tuple(reversed(set_values)),
            flags=set_values,
        ),
        decision=DecisionContext("brother", 1, 2, False, True, "BEFORE_ACTION"),
        turn_state=TurnState(),
        environment=Environment("DAY", effect_ids=tuple(reversed(set_values))),
        tiles=tuple(reversed(tiles)) if reverse else tiles,
        combatants=tuple(reversed(actors)) if reverse else actors,
        action_affordances=ActionAffordanceSet(
            "brother", "", source_generation, AffordanceCompleteness.COMPLETE, (action,)
        ),
        annotations={"expected_best": "attack:enemy"},
    )
    return TacticalState.create(**values)


def test_player_legal_preview_does_not_require_hidden_defense() -> None:
    state = _state()
    enemy = next(actor for actor in state.combatants if actor.actor_id == "enemy")
    action = state.action_affordances.actions[0]

    assert action.preview.displayed_hit_chance.value == 67  # type: ignore[union-attr]
    assert (
        action.preview.displayed_hit_chance.stage  # type: ignore[union-attr]
        is ResolutionStage.PREVIEW_RESOLVED
    )
    assert action.debug_ground_truth is None
    assert enemy.resources.morale.representation is Representation.UNKNOWN
    serialized_action = state.to_dict()["action_affordances"]["actions"][0]  # type: ignore[index]
    assert serialized_action["debug_ground_truth"] is None


def test_round_trip_is_lossless_and_order_is_normalized() -> None:
    first = _state()
    reordered = _state(reverse=True)

    assert first.state_id == reordered.state_id
    assert TacticalState.from_dict(first.to_dict()) == first
    assert [tile.tile_id for tile in reordered.tiles] == ["east", "origin"]
    assert [actor.actor_id for actor in reordered.combatants] == ["brother", "enemy"]
    debug = _state(InformationProfile.OMNISCIENT_DEBUG)
    assert TacticalState.from_dict(debug.to_dict()) == debug
    assert debug.action_affordances.actions[0].debug_ground_truth == {
        "enemy_melee_defense": 12
    }


def test_extended_combat_and_tile_state_preserves_knowledge_fidelity() -> None:
    state = _state()
    active = state.combatants[0]

    assert active.resources.maximum_head_armor.value == 50
    assert active.resources.maximum_body_armor.value == 80
    assert active.resources.initiative.value == 105
    assert active.skills[0].enabled.value is True
    assert (
        active.tactical_stats[0].value.knowledge_class is KnowledgeClass.EXACT_OBSERVED
    )
    assert active.perks.representation is Representation.SET
    assert active.traits.representation is Representation.SET
    origin = next(tile for tile in state.tiles if tile.tile_id == "origin")
    assert origin.movement_cost.representation is Representation.DISTRIBUTION
    assert TacticalState.from_dict(state.to_dict()) == state


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
    debug = _state(InformationProfile.OMNISCIENT_DEBUG)
    action = replace(
        debug.action_affordances.actions[0], debug_ground_truth={"different": True}
    )
    changed_oracle = replace(
        debug,
        state_id="",
        action_affordances=replace(debug.action_affordances, actions=(action,)),
    )

    assert changed_annotations.normalized().state_id == state.state_id
    assert changed_oracle.normalized().state_id == debug.state_id


def test_player_legal_rejects_affordance_debug_oracle() -> None:
    state = _state()
    leaked_action = replace(
        state.action_affordances.actions[0],
        debug_ground_truth={"enemy_melee_defense": 12},
    )
    leaked = replace(
        state,
        state_id="",
        action_affordances=replace(state.action_affordances, actions=(leaked_action,)),
    )

    with pytest.raises(ValueError, match="affordance DEBUG_GROUND_TRUTH"):
        leaked.normalized()


def test_set_like_collections_and_epistemic_sets_normalize_for_hashing() -> None:
    first = _state()
    reordered = _state(reverse_sets=True)

    assert first.state_id == reordered.state_id
    assert first.battle.hostile_faction_ids == ("a", "z")
    assert first.battle.allied_faction_ids == ("a", "z")
    assert first.battle.flags == ("a", "z")
    assert first.environment.effect_ids == ("a", "z")
    assert all(tile.dynamic_effects.candidates == ("a", "z") for tile in first.tiles)
    assert first.combatants[0].perks.candidates == ("perk.a", "perk.z")
    assert first.combatants[0].traits.candidates == ("trait.a", "trait.z")
    origin = next(tile for tile in first.tiles if tile.tile_id == "origin")
    assert origin.movement_cost.distribution == ((1, 0.6), (2, 0.4))
    assert origin.movement_cost.basis == ("a", "z")


def test_profile_changes_semantic_identity_for_same_raw_capture() -> None:
    legal = _state()
    debug = _state(InformationProfile.OMNISCIENT_DEBUG)

    assert legal.raw_capture_id == debug.raw_capture_id
    assert legal.state_id != debug.state_id


def test_raw_capture_linkage_does_not_change_semantic_identity() -> None:
    state = _state()
    another_capture = replace(state, state_id="", raw_capture_id="capture-2")

    assert another_capture.normalized().state_id == state.state_id


def test_affordance_acquisition_metadata_does_not_change_semantic_identity() -> None:
    fixture = _state()
    captured = _state(
        source_generation="game-capture-generation-99",
        provenance=AffordanceProvenance.GAME_PLAYER_AFFORDANCE,
    )

    assert fixture.state_id == captured.state_id
    assert fixture.action_affordances.source_generation != (
        captured.action_affordances.source_generation
    )
    assert fixture.action_affordances.actions[0].provenance is (
        AffordanceProvenance.HANDCRAFTED_FIXTURE
    )
    assert captured.action_affordances.actions[0].provenance is (
        AffordanceProvenance.GAME_PLAYER_AFFORDANCE
    )


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

    movement_leak = replace(
        state.tiles[0],
        traversable=KnownValue.exact(True, KnowledgeClass.DEBUG_GROUND_TRUTH),
    )
    dynamic_tile_leak = replace(
        state,
        state_id="",
        tiles=(movement_leak, state.tiles[1]),
    )
    with pytest.raises(ValueError, match="DEBUG_GROUND_TRUTH"):
        dynamic_tile_leak.normalized()


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
        target_kind=None,
        target_actor_id=None,
        source_location="bag:0",
        target_slot="main_hand",
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


def test_active_actor_requires_exact_placement() -> None:
    state = _state()
    active = replace(state.combatants[0], position=KnownValue.unknown())
    unplaced = replace(
        state,
        state_id="",
        combatants=(active, state.combatants[1]),
        tiles=(replace(state.tiles[0], occupant_actor_id=None), state.tiles[1]),
    )

    with pytest.raises(ValueError, match="exact current position"):
        unplaced.normalized()


def test_move_to_path_cannot_teleport_between_non_adjacent_steps() -> None:
    state = _state()
    move = replace(
        state.action_affordances.actions[0],
        action_id="move:east",
        kind=ActionKind.MOVE_TO,
        skill_id=None,
        target_kind=None,
        target_actor_id=None,
        destination_tile_id="east",
        resolved_path=("origin", "east"),
    )
    teleport = replace(
        state,
        state_id="",
        action_affordances=replace(state.action_affordances, actions=(move,)),
    )

    with pytest.raises(ValueError, match="non-adjacent"):
        teleport.normalized()


def test_skill_affordance_requires_coherent_target_schema() -> None:
    action = _state().action_affordances.actions[0]

    with pytest.raises(ValueError, match="requires skill_id and target_kind"):
        replace(action, target_kind=None, target_actor_id=None)
    with pytest.raises(ValueError, match="target fields do not match"):
        replace(action, target_tile_id="east")
    with pytest.raises(ValueError, match="target_direction must be"):
        replace(
            action,
            target_kind=TargetKind.DIRECTION,
            target_actor_id=None,
            target_direction=6,
        )


def test_skill_target_references_must_resolve_in_snapshot() -> None:
    state = _state()
    action = state.action_affordances.actions[0]
    unknown_actor = replace(action, target_actor_id="missing")
    with pytest.raises(ValueError, match="target_actor_id references unknown"):
        replace(
            state,
            state_id="",
            action_affordances=replace(
                state.action_affordances, actions=(unknown_actor,)
            ),
        ).normalized()

    unknown_tile = replace(
        action,
        target_kind=TargetKind.TILE,
        target_actor_id=None,
        target_tile_id="missing",
    )
    with pytest.raises(ValueError, match="target_tile_id references unknown"):
        replace(
            state,
            state_id="",
            action_affordances=replace(
                state.action_affordances, actions=(unknown_tile,)
            ),
        ).normalized()


def test_affordance_rejects_duplicate_parameters_and_incompatible_fields() -> None:
    action = _state().action_affordances.actions[0]

    with pytest.raises(ValueError, match="duplicate affordance parameter key"):
        replace(
            action,
            parameters=(
                ("rule_fact", KnownValue.exact(1)),
                ("rule_fact", KnownValue.exact(2)),
            ),
        )
    with pytest.raises(ValueError, match="USE_SKILL contains incompatible"):
        replace(action, destination_tile_id="east")
    with pytest.raises(ValueError, match="END_TURN contains incompatible"):
        replace(
            action,
            kind=ActionKind.END_TURN,
            skill_id=None,
            target_kind=None,
            target_actor_id=None,
            destination_tile_id="east",
        )


def test_hidden_hostile_changeable_state_cannot_remain_current_observed_truth() -> None:
    state = _state()
    enemy = state.combatants[1]
    hidden = replace(
        enemy,
        visible=False,
        position=KnownValue.unknown(),
        resources=_resources(),
        last_seen=LastSeen("east", ObservationPoint(1, 1)),
    )
    hidden_state = replace(
        state,
        state_id="",
        combatants=(state.combatants[0], hidden),
        tiles=tuple(
            replace(tile, occupant_actor_id=None) if tile.tile_id == "east" else tile
            for tile in state.tiles
        ),
    )
    with pytest.raises(ValueError, match="numeric state cannot be exact observed"):
        hidden_state.normalized()


def test_visible_hostile_exact_numeric_resources_and_stats_are_rejected() -> None:
    state = _state()
    enemy = state.combatants[1]
    leaked_resources = replace(enemy, resources=_resources())
    with pytest.raises(ValueError, match="numeric state cannot be exact observed"):
        replace(
            state,
            state_id="",
            combatants=(state.combatants[0], leaked_resources),
        ).normalized()

    leaked_stat = replace(
        enemy,
        tactical_stats=(TacticalStat("melee_defense", KnownValue.exact(12)),),
    )
    with pytest.raises(ValueError, match="numeric state cannot be exact observed"):
        replace(
            state,
            state_id="",
            combatants=(state.combatants[0], leaked_stat),
        ).normalized()


def test_hidden_hostile_stale_equipment_and_effects_round_trip() -> None:
    state = _state()
    enemy = state.combatants[1]
    seen = ObservationPoint(1, 1)

    def remembered(value: object) -> KnownValue:
        return KnownValue(
            Representation.EXACT,
            KnowledgeClass.REMEMBERED,
            value=value,  # type: ignore[arg-type]
            observed_at=seen,
        )

    hidden = replace(
        enemy,
        visible=False,
        position=KnownValue.unknown(),
        resources=_unknown_resources(),
        equipment=(
            ItemState(
                "enemy-weapon",
                remembered("item.spear"),
                remembered("main_hand"),
                remembered(True),
            ),
        ),
        effects=(
            EffectState(
                "enemy-effect",
                remembered("effect.example"),
                remembered(True),
            ),
        ),
        last_seen=LastSeen("east", seen),
        content_identity=remembered("enemy.raider"),
        faction=remembered("enemy"),
    )
    rebuilt = TacticalState.create(
        **{item.name: getattr(state, item.name) for item in fields(TacticalState)}
        | {
            "state_id": "",
            "combatants": (state.combatants[0], hidden),
            "tiles": tuple(
                replace(tile, occupant_actor_id=None)
                if tile.tile_id == "east"
                else tile
                for tile in state.tiles
            ),
            "action_affordances": replace(
                state.action_affordances, captured_for_state_id=""
            ),
        }
    )
    assert TacticalState.from_dict(rebuilt.to_dict()) == rebuilt


def test_hidden_hostile_skill_stats_perks_and_traits_must_be_stale() -> None:
    state = _state()
    enemy = state.combatants[1]
    hidden = replace(
        enemy,
        visible=False,
        position=KnownValue.unknown(),
        resources=_unknown_resources(),
        skills=(SkillState("skill.hidden", KnownValue.exact(True)),),
        tactical_stats=(TacticalStat("melee_skill", KnownValue.exact(70)),),
        perks=KnownValue(
            Representation.SET,
            KnowledgeClass.EXACT_OBSERVED,
            candidates=("perk.hidden",),
        ),
        traits=KnownValue.exact(["trait.hidden"]),
        last_seen=LastSeen("east", ObservationPoint(1, 1)),
    )
    hidden_state = replace(
        state,
        state_id="",
        combatants=(state.combatants[0], hidden),
        tiles=tuple(
            replace(tile, occupant_actor_id=None) if tile.tile_id == "east" else tile
            for tile in state.tiles
        ),
    )

    with pytest.raises(ValueError, match="numeric state cannot be exact observed"):
        hidden_state.normalized()


def test_action_ids_are_canonicalized_from_semantic_command_intent() -> None:
    state = _state()
    action = state.action_affordances.actions[0]
    duplicate = replace(action, action_id="caller-chose-another-id")
    duplicated = replace(
        state,
        state_id="",
        action_affordances=replace(
            state.action_affordances, actions=(action, duplicate)
        ),
    )

    normalized = duplicated.normalized()
    assert len(normalized.action_affordances.actions) == 1
    assert normalized.action_affordances.actions[0].action_id.startswith("action:")
    arbitrary_single = replace(
        state,
        state_id="",
        action_affordances=replace(state.action_affordances, actions=(duplicate,)),
    ).normalized()
    assert arbitrary_single.action_affordances.actions[0].action_id == action.action_id


def test_extension_values_are_epistemic_and_reject_debug_leaks() -> None:
    state = _state()
    leaked_action = replace(
        state.action_affordances.actions[0],
        parameters=(
            (
                "extension.hidden_fact",
                KnownValue.exact(7, KnowledgeClass.DEBUG_GROUND_TRUTH),
            ),
        ),
    )
    with pytest.raises(ValueError, match="extension DEBUG_GROUND_TRUTH"):
        replace(
            state,
            state_id="",
            action_affordances=replace(
                state.action_affordances, actions=(leaked_action,)
            ),
        ).normalized()


def test_ground_entities_round_trip_normalize_and_reject_debug_leaks() -> None:
    state = _state()
    entity = GroundEntity(
        "corpse-1",
        KnownValue.exact("entity.corpse"),
        state=(("usable", KnownValue.exact(True)),),
    )
    rebuilt = TacticalState.create(
        **{item.name: getattr(state, item.name) for item in fields(TacticalState)}
        | {
            "state_id": "",
            "ground_entities": (entity,),
            "action_affordances": replace(
                state.action_affordances, captured_for_state_id=""
            ),
        }
    )
    assert TacticalState.from_dict(rebuilt.to_dict()) == rebuilt
    with pytest.raises(ValueError, match="duplicate ground entity"):
        replace(rebuilt, state_id="", ground_entities=(entity, entity)).normalized()

    leaked = replace(
        entity,
        content=KnownValue.exact("entity.hidden", KnowledgeClass.DEBUG_GROUND_TRUTH),
    )
    with pytest.raises(ValueError, match="ground entity DEBUG_GROUND_TRUTH"):
        replace(rebuilt, state_id="", ground_entities=(leaked,)).normalized()


def test_preview_authority_is_closed_and_debug_authority_is_profile_gated() -> None:
    with pytest.raises(ValueError, match="valid authority"):
        ResolvedPreviewValue(
            67,
            ResolutionStage.PREVIEW_RESOLVED,
            "runtime oracle",  # type: ignore[arg-type]
        )

    state = _state()
    action = state.action_affordances.actions[0]
    debug_preview = replace(
        action.preview,
        displayed_hit_chance=ResolvedPreviewValue(
            67,
            ResolutionStage.PREVIEW_RESOLVED,
            ResolutionAuthority.DEBUG_ORACLE,
        ),
    )
    with pytest.raises(ValueError, match="DEBUG_ORACLE preview"):
        replace(
            state,
            state_id="",
            action_affordances=replace(
                state.action_affordances,
                actions=(replace(action, preview=debug_preview),),
            ),
        ).normalized()


def test_cost_authority_is_closed_and_debug_authority_is_profile_gated() -> None:
    with pytest.raises(ValueError, match="valid authority"):
        ResolvedCost(
            4,
            ResolutionStage.PREVIEW_RESOLVED,
            "runtime oracle",  # type: ignore[arg-type]
        )

    state = _state()
    action = replace(
        state.action_affordances.actions[0],
        ap_cost=ResolvedCost(
            4,
            ResolutionStage.PREVIEW_RESOLVED,
            ResolutionAuthority.DEBUG_ORACLE,
        ),
    )
    with pytest.raises(ValueError, match="DEBUG_ORACLE cost"):
        replace(
            state,
            state_id="",
            action_affordances=replace(state.action_affordances, actions=(action,)),
        ).normalized()


def test_complete_affordance_set_requires_actions_and_source_generation() -> None:
    with pytest.raises(ValueError, match="at least one action"):
        ActionAffordanceSet(
            "brother",
            "state-id",
            "generation-1",
            AffordanceCompleteness.COMPLETE,
            (),
        )
    with pytest.raises(ValueError, match="source_generation cannot be empty"):
        ActionAffordanceSet(
            "brother",
            "state-id",
            "",
            AffordanceCompleteness.INCOMPLETE,
            (),
        )


def test_closed_enums_reject_raw_strings_on_direct_construction() -> None:
    debug = _state(InformationProfile.OMNISCIENT_DEBUG)
    with pytest.raises(ValueError, match="information_profile requires"):
        replace(debug, information_profile="player_legal")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="affordance kind requires"):
        replace(
            debug.action_affordances.actions[0],
            kind="USE_SKILL",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="resolved cost stage requires"):
        ResolvedCost(
            4,
            "PREVIEW_RESOLVED",  # type: ignore[arg-type]
            ResolutionAuthority.PLAYER_UI,
        )
    with pytest.raises(ValueError, match="representation requires"):
        KnownValue(  # type: ignore[arg-type]
            "UNKNOWN",
            KnowledgeClass.UNKNOWN,
        )


def test_every_affordance_requires_explicit_resolved_costs() -> None:
    action = _state().action_affordances.actions[0]
    with pytest.raises(ValueError, match="requires resolved AP and fatigue costs"):
        replace(action, ap_cost=None)
    with pytest.raises(ValueError, match="requires resolved AP and fatigue costs"):
        replace(action, fatigue_cost=None)

    zero = ResolvedCost(
        0,
        ResolutionStage.PREVIEW_RESOLVED,
        ResolutionAuthority.HANDCRAFTED_FIXTURE,
    )
    wait = ActionAffordance(
        "temporary-id",
        "brother",
        ActionKind.WAIT,
        AffordanceProvenance.HANDCRAFTED_FIXTURE,
        "generation-1",
        ap_cost=zero,
        fatigue_cost=zero,
    )
    end_turn = replace(wait, kind=ActionKind.END_TURN)
    assert wait.ap_cost.value == end_turn.fatigue_cost.value == 0


@pytest.mark.parametrize("value", [True, 1.5])
def test_resolved_cost_requires_non_bool_integer(value: object) -> None:
    with pytest.raises(ValueError, match="resolved cost value requires an integer"):
        ResolvedCost(
            value,  # type: ignore[arg-type]
            ResolutionStage.PREVIEW_RESOLVED,
            ResolutionAuthority.PLAYER_UI,
        )


@pytest.mark.parametrize("value", [True, 1.5])
def test_integral_snapshot_fields_reject_bool_and_float(value: object) -> None:
    with pytest.raises(ValueError, match="observation round requires an integer"):
        ObservationPoint(value, 1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="hex q requires an integer"):
        HexCoord(value, 0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="tile elevation requires an integer"):
        replace(_state().tiles[0], elevation=value)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="decision round requires an integer"):
        replace(_state().decision, round=value)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-negative integers"):
        replace(_resources(), hit_points=KnownValue.exact(value))  # type: ignore[arg-type]


def test_integral_fields_deserialize_with_same_domain_and_round_trip() -> None:
    state = _state()
    assert TacticalState.from_dict(state.to_dict()) == state
    invalid = state.to_dict()
    invalid["decision"]["round"] = 1.5  # type: ignore[index]
    with pytest.raises(TypeError, match="expected int"):
        TacticalState.from_dict(invalid)


@pytest.mark.parametrize("value", [True, 67.5])
def test_displayed_hit_chance_requires_non_bool_integer(value: object) -> None:
    with pytest.raises(ValueError, match="integer in"):
        PlayerVisiblePreview(
            displayed_hit_chance=ResolvedPreviewValue(
                value,  # type: ignore[arg-type]
                ResolutionStage.PREVIEW_RESOLVED,
                ResolutionAuthority.PLAYER_UI,
            )
        )


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
    with pytest.raises(ValueError, match="incompatible payload"):
        KnownValue(
            Representation.UNKNOWN,
            KnowledgeClass.UNKNOWN,
            minimum=-1,
        )


@pytest.mark.parametrize(
    ("representation", "kwargs"),
    [
        (Representation.EXACT, {"value": 1, "candidates": (1,)}),
        (Representation.RANGE, {"minimum": 1, "maximum": 2, "value": 1}),
        (Representation.SET, {"candidates": (1,), "minimum": 0}),
        (
            Representation.DISTRIBUTION,
            {"distribution": ((1, 1.0),), "value": 1},
        ),
    ],
)
def test_knowledge_representations_reject_cross_payload_smuggling(
    representation: Representation, kwargs: dict[str, object]
) -> None:
    with pytest.raises(ValueError, match="incompatible payload"):
        KnownValue(
            representation,
            KnowledgeClass.EXACT_OBSERVED,
            **kwargs,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("minimum", "maximum"),
    [
        (True, 2),
        (1, False),
        (float("nan"), 2),
        (1, float("inf")),
    ],
)
def test_range_endpoints_require_finite_non_bool_numbers(
    minimum: object, maximum: object
) -> None:
    with pytest.raises(ValueError, match="finite non-bool numbers"):
        KnownValue(
            Representation.RANGE,
            KnowledgeClass.INFERRED,
            minimum=minimum,  # type: ignore[arg-type]
            maximum=maximum,  # type: ignore[arg-type]
            basis=("evidence",),
        )


@pytest.mark.parametrize("confidence", [True, 1, float("nan"), float("inf")])
def test_confidence_requires_finite_float(confidence: object) -> None:
    with pytest.raises(ValueError, match="finite float"):
        KnownValue(
            Representation.EXACT,
            KnowledgeClass.INFERRED,
            value=1,
            basis=("evidence",),
            confidence=confidence,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "probability",
    [True, 1, float("nan"), float("inf"), float("-inf")],
)
def test_distribution_probabilities_require_finite_floats(
    probability: object,
) -> None:
    with pytest.raises(ValueError, match="finite nonnegative floats"):
        KnownValue(
            Representation.DISTRIBUTION,
            KnowledgeClass.INFERRED,
            distribution=(("outcome", probability),),  # type: ignore[arg-type]
            basis=("evidence",),
        )


def test_state_round_trip_preserves_valid_uncertainty_numeric_metadata() -> None:
    state = _state()
    enemy = replace(
        state.combatants[1],
        tactical_stats=(
            TacticalStat(
                "melee_defense",
                KnownValue(
                    Representation.RANGE,
                    KnowledgeClass.INFERRED,
                    minimum=8,
                    maximum=18,
                    basis=("observed_hit_chance",),
                    confidence=0.75,
                ),
            ),
        ),
    )
    rebuilt = TacticalState.create(
        **{item.name: getattr(state, item.name) for item in fields(TacticalState)}
        | {
            "state_id": "",
            "combatants": (state.combatants[0], enemy),
            "action_affordances": replace(
                state.action_affordances, captured_for_state_id=""
            ),
        }
    )

    loaded = TacticalState.from_dict(rebuilt.to_dict())
    assert loaded == rebuilt
    assert loaded.combatants[1].tactical_stats[0].value.confidence == 0.75
    origin = next(tile for tile in loaded.tiles if tile.tile_id == "origin")
    assert origin.movement_cost.distribution == ((1, 0.6), (2, 0.4))


def test_json_payloads_are_deep_frozen_against_caller_mutation() -> None:
    source = [{"tile": "east"}]
    known = KnownValue.exact(source)
    preview_source = {"path": ["east"]}
    preview = ResolvedPreviewValue(
        preview_source,
        ResolutionStage.PREVIEW_RESOLVED,
        ResolutionAuthority.PLAYER_UI,
    )

    source[0]["tile"] = "mutated"
    preview_source["path"].append("mutated")
    assert known.value[0]["tile"] == "east"  # type: ignore[index]
    assert preview.value["path"] == ("east",)  # type: ignore[index]
    with pytest.raises(TypeError):
        known.value[0]["tile"] = "blocked"  # type: ignore[index]
    with pytest.raises(TypeError):
        preview.value["new"] = True  # type: ignore[index]


def test_from_dict_deep_freezes_payloads_and_round_trips() -> None:
    state = _state()
    serialized = state.to_dict()
    loaded = TacticalState.from_dict(serialized)
    serialized["annotations"]["expected_best"] = "mutated"  # type: ignore[index]
    assert loaded.annotations["expected_best"] == "attack:enemy"  # type: ignore[index]
    assert TacticalState.from_dict(loaded.to_dict()) == loaded


@pytest.mark.parametrize(
    "position",
    [
        KnownValue(
            Representation.SET,
            KnowledgeClass.OBSERVED,
            candidates=("east",),
        ),
        KnownValue(
            Representation.EXACT,
            KnowledgeClass.REMEMBERED,
            value="east",
            observed_at=ObservationPoint(1, 1),
        ),
    ],
)
def test_hidden_hostile_current_position_rejects_observed_and_remembered_payloads(
    position: KnownValue,
) -> None:
    state = _state()
    hidden = replace(
        state.combatants[1],
        visible=False,
        position=position,
        resources=_unknown_resources(),
        last_seen=LastSeen("east", ObservationPoint(1, 1)),
    )
    with pytest.raises(ValueError, match="must be UNKNOWN or INFERRED"):
        replace(
            state,
            state_id="",
            combatants=(state.combatants[0], hidden),
            tiles=tuple(
                replace(tile, occupant_actor_id=None)
                if tile.tile_id == "east"
                else tile
                for tile in state.tiles
            ),
        ).normalized()


def test_hidden_hostile_inferred_position_with_last_seen_round_trips() -> None:
    state = _state()
    hidden = replace(
        state.combatants[1],
        visible=False,
        position=KnownValue(
            Representation.SET,
            KnowledgeClass.INFERRED,
            candidates=("east", "origin"),
            basis=("movement_bound",),
        ),
        resources=_unknown_resources(),
        last_seen=LastSeen("east", ObservationPoint(1, 1)),
    )
    rebuilt = TacticalState.create(
        **{item.name: getattr(state, item.name) for item in fields(TacticalState)}
        | {
            "state_id": "",
            "combatants": (state.combatants[0], hidden),
            "tiles": tuple(
                replace(tile, occupant_actor_id=None)
                if tile.tile_id == "east"
                else tile
                for tile in state.tiles
            ),
            "action_affordances": replace(
                state.action_affordances, captured_for_state_id=""
            ),
        }
    )
    assert TacticalState.from_dict(rebuilt.to_dict()) == rebuilt
