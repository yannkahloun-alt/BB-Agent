from dataclasses import fields, replace

from bb_agent.features import extract_candidate_features
from bb_agent.results import ResultStatus
from bb_agent.tactical_state import (
    ActionKind,
    Combatant,
    HexCoord,
    InformationProfile,
    KnowledgeClass,
    KnownValue,
    LifeState,
    Relation,
    Representation,
    TacticalState,
    Tile,
)
from test_mechanics import (
    _authority,
    _move_action,
    _movement_state,
    _ordinary_attack_state,
    _reaction,
    _resource_action,
    _snapshot,
    _wait,
)


def _rebuild(state: TacticalState, **changes) -> TacticalState:
    values = {field.name: getattr(state, field.name) for field in fields(state)}
    values.update(state_id="")
    values.update(changes)
    return TacticalState.create(**values)


def _known_position(actor: Combatant, tile_id: str) -> Combatant:
    return replace(
        actor,
        position=KnownValue.exact(tile_id),
        visible=True,
        life_state=LifeState.ALIVE,
    )


def _tiles(
    coordinates: dict[str, tuple[int, int]],
    actors: tuple[Combatant, ...],
    *,
    elevations: dict[str, int] | None = None,
    los_blocks: frozenset[str] = frozenset(),
) -> tuple[Tile, ...]:
    elevations = elevations or {}
    coords = {tile_id: HexCoord(*coord) for tile_id, coord in coordinates.items()}
    by_coord = {coord: tile_id for tile_id, coord in coords.items()}
    occupants = {
        actor.position.value: actor.actor_id
        for actor in actors
        if actor.life_state is LifeState.ALIVE
        and actor.position.representation is Representation.EXACT
        and isinstance(actor.position.value, str)
    }
    return tuple(
        Tile(
            tile_id,
            coord,
            elevations.get(tile_id, 0),
            KnownValue.exact("plain"),
            tuple(by_coord.get(coord.neighbor(direction)) for direction in range(6)),
            occupants.get(tile_id),
            blocking=KnownValue.exact(False),
            traversable=KnownValue.exact(True),
            blocks_line_of_sight=KnownValue.exact(tile_id in los_blocks),
        )
        for tile_id, coord in coords.items()
    )


def _formation_state(
    *,
    start: str,
    destination: str,
    elevations: dict[str, int] | None = None,
) -> TacticalState:
    authority = _authority()
    base = _snapshot(authority, _move_action())
    brother = next(actor for actor in base.combatants if actor.actor_id == "brother")
    enemy = next(actor for actor in base.combatants if actor.actor_id == "enemy")
    ally = replace(
        brother,
        actor_id="ally",
        relation=Relation.PLAYER,
        is_player_controlled=False,
        resources=replace(
            brother.resources,
            hit_points=KnownValue.exact(10),
            maximum_hit_points=KnownValue.exact(60),
        ),
    )
    actors = (
        _known_position(brother, start),
        _known_position(ally, "back"),
        _known_position(enemy, "front"),
    )
    coordinates = {
        "screen": (0, 0),
        "front": (1, 0),
        "back": (-1, 0),
        "flank": (0, 1),
        "escape": (1, 1),
        "rear_escape": (-1, 1),
    }
    move = _move_action(destination=destination, path=(destination,))
    return _snapshot(
        authority,
        move,
        information_profile=InformationProfile.OMNISCIENT_DEBUG,
        combatants=actors,
        tiles=_tiles(coordinates, actors, elevations=elevations),
    )


def _features(state: TacticalState):
    authority = _authority()
    action_id = state.action_affordances.actions[0].action_id
    result = extract_candidate_features(authority, state, action_id)
    assert result.status is ResultStatus.SUCCESS
    assert result.value is not None
    return result.value


def test_zero_damage_move_can_create_protection_position_and_future_capacity():
    state = _formation_state(
        start="flank",
        destination="screen",
        elevations={"screen": 1},
    )

    features = _features(state)

    assert features.enemy_effect.expected_hp_damage.expected == 0
    assert features.formation.created_direct_screen_links.expected == 1
    assert features.formation.possibly_newly_screened_ally_ids == ("ally",)
    assert features.position.elevation_change.expected == 1
    assert features.future_capacity.ap_fat_feasible_template_count.expected == 1


def test_vacating_direct_screen_exposes_the_vulnerable_ally_as_raw_fact():
    state = _formation_state(start="screen", destination="flank")

    features = _features(state)

    assert features.formation.lost_direct_screen_links.expected == 1
    assert features.formation.possibly_exposed_ally_ids == ("ally",)
    ally = next(actor for actor in state.combatants if actor.actor_id == "ally")
    assert ally.resources.hit_points.value == 10


def test_high_ground_and_contact_elevation_are_explicit():
    state = _formation_state(
        start="flank",
        destination="screen",
        elevations={"screen": 2, "front": 0},
    )

    features = _features(state)

    assert features.position.elevation.expected == 2
    assert features.position.elevation_change.expected == 2
    assert features.position.elevation_advantage_contacts.minimum == 1


def test_surround_pressure_is_separate_from_unproven_zoc_capability():
    authority = _authority()
    base = _snapshot(authority, _move_action())
    brother = next(actor for actor in base.combatants if actor.actor_id == "brother")
    enemy = next(actor for actor in base.combatants if actor.actor_id == "enemy")
    ally = replace(
        brother,
        actor_id="ally",
        relation=Relation.PLAYER,
        is_player_controlled=False,
    )
    enemy2 = replace(enemy, actor_id="enemy-2")
    actors = (
        _known_position(brother, "start"),
        _known_position(ally, "ally"),
        _known_position(enemy, "enemy-1"),
        _known_position(enemy2, "enemy-2"),
    )
    coordinates = {
        "center": (0, 0),
        "start": (-1, 1),
        "ally": (1, -1),
        "enemy-1": (1, 0),
        "enemy-2": (0, 1),
    }
    state = _snapshot(
        authority,
        _move_action(destination="center", path=("center",)),
        information_profile=InformationProfile.OMNISCIENT_DEBUG,
        combatants=actors,
        tiles=_tiles(coordinates, actors),
    )

    features = _features(state)

    assert features.threat.adjacent_hostile_pressure.expected == 2
    assert features.threat.hostile_zoc_pressure.minimum == 0
    assert features.threat.hostile_zoc_pressure.maximum == 2
    assert features.threat.hostile_zoc_pressure.expected is None
    assert features.control.flanked_hostiles.minimum >= 1


def test_fat_heavy_action_reduces_headroom_and_locks_current_cost_templates():
    authority = _authority()
    reload_action = _resource_action("actives.reload_bolt")
    move = _move_action(destination="east", path=("east",), fatigue=10)
    state = _snapshot(authority, reload_action, move)
    actors = tuple(
        replace(
            actor,
            resources=replace(
                actor.resources,
                fatigue_capacity=KnownValue.exact(25),
            ),
        )
        if actor.actor_id == "brother"
        else actor
        for actor in state.combatants
    )
    state = _rebuild(state, combatants=actors)
    reload_id = next(
        action.action_id
        for action in state.action_affordances.actions
        if action.skill_id == "actives.reload_bolt"
    )

    result = extract_candidate_features(authority, state, reload_id)

    assert result.status is ResultStatus.SUCCESS
    assert result.value is not None
    assert result.value.resources.fatigue.expected == 20
    assert result.value.resources.fatigue_headroom.expected == 5
    assert result.value.resources.ammo_consumed == 1
    assert result.value.future_capacity.current_cost_template_count == 2
    assert result.value.future_capacity.ap_fat_feasible_template_count.expected == 0
    assert result.value.future_capacity.ap_fat_locked_template_count.expected == 2


def test_ranged_los_exposure_uses_known_blocking_without_attack_odds():
    authority = _authority()
    wait = _wait()
    base = _snapshot(authority, wait)
    brother = next(actor for actor in base.combatants if actor.actor_id == "brother")
    enemy = next(actor for actor in base.combatants if actor.actor_id == "enemy")
    actors = (
        _known_position(brother, "origin"),
        _known_position(enemy, "far"),
    )
    coordinates = {"origin": (0, 0), "middle": (1, 0), "far": (2, 0)}
    clear = _snapshot(
        authority,
        wait,
        information_profile=InformationProfile.OMNISCIENT_DEBUG,
        combatants=actors,
        tiles=_tiles(coordinates, actors),
    )
    blocked = _rebuild(
        clear,
        tiles=_tiles(coordinates, actors, los_blocks=frozenset(("middle",))),
    )

    clear_features = _features(clear)
    blocked_features = _features(blocked)

    assert clear_features.threat.ranged_los_exposure.expected == 1
    assert blocked_features.threat.ranged_los_exposure.expected == 0


def test_safe_and_unsafe_repositioning_preserve_aoo_consequences():
    authority = _authority()
    safe = _movement_state(authority, _move_action(), enemy_far=True)
    unsafe = _movement_state(
        authority,
        _move_action(reactions=(_reaction(),)),
    )
    safe_id = safe.action_affordances.actions[0].action_id
    unsafe_id = unsafe.action_affordances.actions[0].action_id

    safe_result = extract_candidate_features(authority, safe, safe_id)
    unsafe_result = extract_candidate_features(authority, unsafe, unsafe_id)

    assert safe_result.status is ResultStatus.SUCCESS
    assert unsafe_result.status is ResultStatus.SUCCESS
    assert safe_result.value is not None
    assert unsafe_result.value is not None
    assert safe_result.value.mobility.movement_completion_probability.expected == 1
    assert (
        safe_result.value.friendly_harm.movement_interruption_probability.expected == 0
    )
    assert unsafe_result.value.mobility.movement_completion_probability.expected < 1
    assert (
        unsafe_result.value.friendly_harm.movement_interruption_probability.expected > 0
    )
    assert unsafe_result.value.friendly_harm.expected_self_hp_damage.maximum > 0


def test_uncertain_hostile_position_stays_a_threat_range_without_midpoint():
    authority = _authority()
    wait = _wait()
    base = _snapshot(authority, wait)
    brother = next(actor for actor in base.combatants if actor.actor_id == "brother")
    enemy = next(actor for actor in base.combatants if actor.actor_id == "enemy")
    enemy = replace(
        enemy,
        visible=False,
        position=KnownValue(
            Representation.SET,
            KnowledgeClass.INFERRED,
            candidates=("adjacent", "far"),
            basis=("fixture-visible-bounds",),
        ),
    )
    actors = (_known_position(brother, "origin"), enemy)
    coordinates = {
        "origin": (0, 0),
        "adjacent": (1, 0),
        "middle": (2, 0),
        "far": (3, 0),
    }
    state = _snapshot(
        authority,
        wait,
        information_profile=InformationProfile.PLAYER_LEGAL,
        combatants=actors,
        tiles=_tiles(coordinates, actors),
    )

    features = _features(state)

    assert features.threat.adjacent_hostile_pressure.minimum == 0
    assert features.threat.adjacent_hostile_pressure.maximum == 1
    assert features.threat.adjacent_hostile_pressure.expected is None


def test_attack_enemy_effect_and_wait_end_turn_tempo_are_raw_not_scored():
    authority = _authority()
    attack_state = _ordinary_attack_state(authority)
    attack_id = attack_state.action_affordances.actions[0].action_id
    attack_result = extract_candidate_features(authority, attack_state, attack_id)

    assert attack_result.status is ResultStatus.SUCCESS
    assert attack_result.value is not None
    assert attack_result.value.enemy_effect.expected_hp_damage.expected > 0
    assert attack_result.value.enemy_effect.expected_armor_damage.expected > 0
    assert 0 <= attack_result.value.enemy_effect.kill_probability.expected <= 1
    assert attack_result.value.resources.remaining_action_points.expected == 5
    assert attack_result.value.resources.fatigue.expected == 10

    wait_state = _snapshot(authority, _wait())
    wait_features = _features(wait_state)
    assert wait_features.tempo.actor_has_waited.expected == 1
    assert wait_features.tempo.actor_may_wait.expected == 0
    assert wait_features.tempo.turn_ended.expected == 0

    end_state = _snapshot(authority, _wait(ActionKind.END_TURN))
    end_features = _features(end_state)
    assert end_features.tempo.turn_ended.expected == 1


def test_feature_output_is_deterministic_for_identical_state_and_candidate():
    state = _formation_state(start="flank", destination="screen")
    authority = _authority()
    action_id = state.action_affordances.actions[0].action_id

    first = extract_candidate_features(authority, state, action_id)
    second = extract_candidate_features(authority, state, action_id)

    assert first.status is ResultStatus.SUCCESS
    assert first == second


def test_feature_extractor_resolves_canonical_action_not_divergent_copy():
    state = _formation_state(start="flank", destination="screen")
    authority = _authority()
    action = state.action_affordances.actions[0]
    divergent = replace(
        action,
        ap_cost=replace(action.ap_cost, value=9),
        fatigue_cost=replace(action.fatigue_cost, value=90),
    )

    result = extract_candidate_features(authority, state, divergent)

    assert result.status is ResultStatus.SUCCESS
    assert result.value is not None
    assert result.value.resources.ap_spent == action.ap_cost.value
    assert result.value.resources.fatigue_added == action.fatigue_cost.value
