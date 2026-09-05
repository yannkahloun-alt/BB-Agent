"""Raw tactical features for supported current candidates.

This module deliberately stops before #21 policy. It turns canonical #40
candidate outcomes/transitions into deterministic, inspectable facts and bounded
spatial proxies. It never generates a second command, infers an enemy action,
or replaces uncertain player-legal knowledge with debug truth.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from enum import IntEnum

from bb_agent.candidates import (
    CandidateReference,
    EvaluationInvalid,
    EvaluationUnsupported,
    evaluation_failure_result,
    resolve_current_candidate,
)
from bb_agent.mechanics import MechanicsAuthority
from bb_agent.outcomes import AttackOutcome, OutcomeBranch, evaluate_ordinary_attack
from bb_agent.results import Result
from bb_agent.tactical_state import (
    ActionAffordance,
    ActionKind,
    Combatant,
    HexCoord,
    KnownValue,
    LifeState,
    Relation,
    Representation,
    TacticalState,
    Tile,
)
from bb_agent.transitions import TransitionOutcome, evaluate_transition

MODEL_VERSION = "tactical-features.v1"


@dataclass(frozen=True, slots=True)
class MetricRange:
    """A raw metric with bounds and an optional justified expectation."""

    minimum: float
    maximum: float
    expected: float | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.minimum) or not math.isfinite(self.maximum):
            raise ValueError("feature bounds must be finite")
        if self.minimum > self.maximum:
            raise ValueError("feature minimum exceeds maximum")
        if self.expected is not None:
            if not math.isfinite(self.expected):
                raise ValueError("feature expectation must be finite")
            if not self.minimum - 1e-9 <= self.expected <= self.maximum + 1e-9:
                raise ValueError("feature expectation lies outside its bounds")

    @classmethod
    def exact(cls, value: int | float) -> MetricRange:
        number = float(value)
        return cls(number, number, number)


@dataclass(frozen=True, slots=True)
class EnemyEffectFeatures:
    expected_hp_damage: MetricRange
    expected_armor_damage: MetricRange
    kill_probability: MetricRange


@dataclass(frozen=True, slots=True)
class FriendlyHarmFeatures:
    expected_self_hp_damage: MetricRange
    expected_ally_hp_damage: MetricRange
    self_death_probability: MetricRange
    movement_interruption_probability: MetricRange
    contingent_aoo_reactor_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ThreatFeatures:
    adjacent_hostile_pressure: MetricRange
    hostile_zoc_pressure: MetricRange
    ranged_los_exposure: MetricRange


@dataclass(frozen=True, slots=True)
class PositionFeatures:
    elevation: MetricRange
    elevation_change: MetricRange
    elevation_advantage_contacts: MetricRange
    elevation_disadvantage_contacts: MetricRange


@dataclass(frozen=True, slots=True)
class FormationFeatures:
    adjacent_allies: MetricRange
    direct_screen_links: MetricRange
    lost_direct_screen_links: MetricRange
    created_direct_screen_links: MetricRange
    possibly_exposed_ally_ids: tuple[str, ...]
    possibly_newly_screened_ally_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ControlFeatures:
    flanked_hostiles: MetricRange


@dataclass(frozen=True, slots=True)
class MobilityFeatures:
    open_adjacent_reposition_tiles: MetricRange
    movement_completion_probability: MetricRange


@dataclass(frozen=True, slots=True)
class ResourceFeatures:
    remaining_action_points: MetricRange
    fatigue: MetricRange
    fatigue_headroom: MetricRange
    ap_spent: int
    fatigue_added: int
    ammo_consumed: int
    charges_consumed: int
    item_action_cost: int


@dataclass(frozen=True, slots=True)
class FutureCapacityFeatures:
    current_cost_template_ids: tuple[str, ...]
    current_cost_template_count: int
    ap_fat_feasible_template_count: MetricRange
    ap_fat_locked_template_count: MetricRange


@dataclass(frozen=True, slots=True)
class TempoFeatures:
    actor_has_waited: MetricRange
    actor_may_wait: MetricRange
    turn_ended: MetricRange
    known_not_done_turn_entries: int


@dataclass(frozen=True, slots=True)
class FeatureOwnership:
    family: str
    owns: str
    excludes: str


SEMANTIC_OWNERSHIP = (
    FeatureOwnership(
        "enemy_effect",
        "direct hostile HP/armor effect and removal probability from current command",
        "posture/threat does not also credit removal of the attacked target",
    ),
    FeatureOwnership(
        "friendly_harm",
        "immediate self/ally harm and current-move interruption consequences",
        "future hostile pressure and formation geometry",
    ),
    FeatureOwnership(
        "threat",
        "post-action hostile contact/ZOC/LOS exposure proxies",
        "immediate AOO damage and inferred enemy commands or attack probabilities",
    ),
    FeatureOwnership(
        "position",
        "elevation facts and elevation relationship at the resulting posture",
        "formation, control, or damage value",
    ),
    FeatureOwnership(
        "formation",
        "ally adjacency and direct one-hex screen geometry",
        "hostile damage probability, pathfinding, or unit-value policy",
    ),
    FeatureOwnership(
        "control",
        "active actor contribution to a geometric ally-supported flank/surround",
        "incoming adjacent pressure already owned by threat",
    ),
    FeatureOwnership(
        "mobility",
        "known/possible open adjacent tiles and current MOVE_TO completion probability",
        "future MOVE_TO legality, pathfinding, or second-command search",
    ),
    FeatureOwnership(
        "resources",
        "post-command AP/FAT/headroom and explicit resolved resource costs",
        "policy weights or claims that spending a resource is intrinsically bad",
    ),
    FeatureOwnership(
        "future_capacity",
        "AP/FAT affordability of deduplicated current-command cost templates",
        "a claim that those templates remain legal after the command",
    ),
    FeatureOwnership(
        "tempo",
        "known Wait/end-turn/current turn-state facts",
        "initiative prediction or enemy response simulation",
    ),
)


@dataclass(frozen=True, slots=True)
class TacticalFeatures:
    action_id: str
    model_version: str
    outcome_model_version: str
    enemy_effect: EnemyEffectFeatures
    friendly_harm: FriendlyHarmFeatures
    threat: ThreatFeatures
    position: PositionFeatures
    formation: FormationFeatures
    control: ControlFeatures
    mobility: MobilityFeatures
    resources: ResourceFeatures
    future_capacity: FutureCapacityFeatures
    tempo: TempoFeatures
    semantic_ownership: tuple[FeatureOwnership, ...] = SEMANTIC_OWNERSHIP


@dataclass(frozen=True, slots=True)
class _PostureBranch:
    probability: float
    actor: Combatant


class _LineStatus(IntEnum):
    BLOCKED = 0
    UNCERTAIN = 1
    CLEAR = 2


def _invalid(action: ActionAffordance, message: str) -> None:
    raise EvaluationInvalid(
        message,
        path=f"action_affordances.{action.action_id}.features",
    )


def _unsupported(action: ActionAffordance, message: str) -> None:
    raise EvaluationUnsupported(
        message,
        path=f"action_affordances.{action.action_id}.features",
        mechanic_id="tactical_features",
    )


def _exact_int(value: KnownValue, label: str, action: ActionAffordance) -> int:
    if (
        value.representation is not Representation.EXACT
        or isinstance(value.value, bool)
        or not isinstance(value.value, int)
    ):
        _unsupported(action, f"{label} must be exact for tactical features")
    return value.value


def _weighted_range(
    values: Iterable[tuple[float, MetricRange]],
) -> MetricRange:
    items = tuple(values)
    if not items:
        return MetricRange.exact(0)
    minimum = min(metric.minimum for _, metric in items)
    maximum = max(metric.maximum for _, metric in items)
    total_probability = sum(probability for probability, _ in items)
    expected = None
    if abs(total_probability - 1.0) <= 1e-9 and all(
        metric.expected is not None for _, metric in items
    ):
        expected = sum(
            probability * metric.expected  # type: ignore[operator]
            for probability, metric in items
        )
    return MetricRange(minimum, maximum, expected)


def _branch_expectation(
    branches: tuple[OutcomeBranch, ...],
    selector: Callable[[OutcomeBranch], float],
) -> float:
    return sum(branch.probability * selector(branch) for branch in branches)


def _attack_metric(
    outcome: AttackOutcome,
    selector: Callable[[OutcomeBranch], float],
) -> MetricRange:
    if outcome.epistemic_scenarios:
        values = tuple(
            _branch_expectation(scenario.branches, selector)
            for scenario in outcome.epistemic_scenarios
        )
        return MetricRange(min(values), max(values))
    value = _branch_expectation(outcome.branches, selector)
    return MetricRange.exact(value)


def _enemy_effect(outcome: AttackOutcome | None) -> EnemyEffectFeatures:
    if outcome is None:
        zero = MetricRange.exact(0)
        return EnemyEffectFeatures(zero, zero, zero)
    return EnemyEffectFeatures(
        _attack_metric(outcome, lambda branch: float(branch.hp_damage)),
        _attack_metric(outcome, lambda branch: float(branch.armor_damage)),
        _attack_metric(outcome, lambda branch: float(branch.killed)),
    )


def _friendly_harm(
    state: TacticalState,
    action: ActionAffordance,
    transition: TransitionOutcome | None,
) -> FriendlyHarmFeatures:
    zero = MetricRange.exact(0)
    if transition is None or not action.contingent_reactions:
        return FriendlyHarmFeatures(zero, zero, zero, zero, ())

    actor = next(
        combatant
        for combatant in state.combatants
        if combatant.actor_id == action.actor_id
    )
    starting_hp = _exact_int(actor.resources.hit_points, "actor HP", action)
    damage_by_branch: list[tuple[float, int]] = []
    death_probability = 0.0
    interruption_probability = 0.0
    for branch in transition.branches:
        ending_hp = _exact_int(
            branch.actor.resources.hit_points,
            "post-action HP",
            action,
        )
        damage_by_branch.append((branch.probability, max(0, starting_hp - ending_hp)))
        if branch.actor.life_state is not LifeState.ALIVE:
            death_probability += branch.probability
        if branch.interrupted:
            interruption_probability += branch.probability

    damage_values = tuple(damage for _, damage in damage_by_branch)
    expected_damage = sum(
        probability * damage for probability, damage in damage_by_branch
    )
    return FriendlyHarmFeatures(
        MetricRange(min(damage_values), max(damage_values), expected_damage),
        zero,
        MetricRange.exact(death_probability),
        MetricRange.exact(interruption_probability),
        tuple(
            sorted(
                {reaction.reacting_actor_id for reaction in action.contingent_reactions}
            )
        ),
    )


def _actor_domain(
    actor: Combatant,
    tile_ids: frozenset[str],
) -> frozenset[str] | None:
    position = actor.position
    if position.representation is Representation.EXACT:
        if isinstance(position.value, str) and position.value in tile_ids:
            return frozenset((position.value,))
        return None
    if position.representation is Representation.SET:
        if all(
            isinstance(item, str) and item in tile_ids for item in position.candidates
        ):
            return frozenset(position.candidates)
        return None
    if position.representation is Representation.DISTRIBUTION:
        if all(
            isinstance(item, str) and item in tile_ids
            for item, _ in position.distribution
        ):
            return frozenset(item for item, _ in position.distribution)
    return None


def _adjacent(tile_by_id: dict[str, Tile], left: str, right: str) -> bool:
    return right in tile_by_id[left].neighbors


def _relation_adjacency_range(
    state: TacticalState,
    actor_tile_id: str,
    relation: Relation,
) -> MetricRange:
    tile_by_id = {tile.tile_id: tile for tile in state.tiles}
    tile_ids = frozenset(tile_by_id)
    has_neighbor = any(
        neighbor is not None for neighbor in tile_by_id[actor_tile_id].neighbors
    )
    minimum = 0
    maximum = 0
    for other in state.combatants:
        if other.actor_id == state.decision.active_actor_id:
            continue
        if other.relation is not relation or other.life_state is not LifeState.ALIVE:
            continue
        domain = _actor_domain(other, tile_ids)
        if domain is None:
            maximum += int(has_neighbor)
            continue
        adjacency = tuple(
            _adjacent(tile_by_id, actor_tile_id, tile_id) for tile_id in domain
        )
        minimum += int(bool(adjacency) and all(adjacency))
        maximum += int(any(adjacency))
    if minimum == maximum:
        return MetricRange.exact(minimum)
    return MetricRange(minimum, maximum)


def _bool_bounds(value: KnownValue) -> tuple[bool, bool]:
    if value.representation is Representation.EXACT and isinstance(value.value, bool):
        return value.value, value.value
    if (
        value.representation is Representation.SET
        and value.candidates
        and all(isinstance(item, bool) for item in value.candidates)
    ):
        return all(value.candidates), any(value.candidates)
    if (
        value.representation is Representation.DISTRIBUTION
        and value.distribution
        and all(isinstance(item, bool) for item, _ in value.distribution)
    ):
        candidates = tuple(item for item, _ in value.distribution)
        return all(candidates), any(candidates)
    return False, True


def _cube_round(q: float, r: float) -> HexCoord:
    x = q
    z = r
    y = -q - r
    rounded_x = round(x)
    rounded_y = round(y)
    rounded_z = round(z)
    x_delta = abs(rounded_x - x)
    y_delta = abs(rounded_y - y)
    z_delta = abs(rounded_z - z)
    if x_delta > y_delta and x_delta > z_delta:
        rounded_x = -rounded_y - rounded_z
    elif y_delta > z_delta:
        rounded_y = -rounded_x - rounded_z
    else:
        rounded_z = -rounded_x - rounded_y
    return HexCoord(int(rounded_x), int(rounded_z))


def _hex_line(
    start: HexCoord,
    end: HexCoord,
    coordinate_to_tile: dict[HexCoord, str],
) -> tuple[str | None, ...]:
    distance = start.distance_to(end)
    if distance == 0:
        return ()
    start_q = start.q + 1e-7
    start_r = start.r + 2e-7
    end_q = end.q + 1e-7
    end_r = end.r + 2e-7
    result: list[str | None] = []
    for step in range(1, distance):
        fraction = step / distance
        coordinate = _cube_round(
            start_q + (end_q - start_q) * fraction,
            start_r + (end_r - start_r) * fraction,
        )
        result.append(coordinate_to_tile.get(coordinate))
    return tuple(result)


def _line_status(
    state: TacticalState,
    actor_tile_id: str,
    hostile_tile_id: str,
) -> _LineStatus:
    tile_by_id = {tile.tile_id: tile for tile in state.tiles}
    actor_tile = tile_by_id[actor_tile_id]
    hostile_tile = tile_by_id[hostile_tile_id]
    if actor_tile.coordinate.distance_to(hostile_tile.coordinate) < 2:
        return _LineStatus.BLOCKED

    coordinate_to_tile = {tile.coordinate: tile.tile_id for tile in state.tiles}
    uncertain = False
    for tile_id in _hex_line(
        actor_tile.coordinate,
        hostile_tile.coordinate,
        coordinate_to_tile,
    ):
        if tile_id is None:
            uncertain = True
            continue
        blocked_minimum, blocked_maximum = _bool_bounds(
            tile_by_id[tile_id].blocks_line_of_sight
        )
        if blocked_minimum:
            return _LineStatus.BLOCKED
        if blocked_maximum:
            uncertain = True
    if uncertain:
        return _LineStatus.UNCERTAIN
    return _LineStatus.CLEAR


def _ranged_los_range(state: TacticalState, actor_tile_id: str) -> MetricRange:
    tile_by_id = {tile.tile_id: tile for tile in state.tiles}
    tile_ids = frozenset(tile_by_id)
    minimum = 0
    maximum = 0
    for hostile in state.combatants:
        if hostile.relation is not Relation.HOSTILE:
            continue
        if hostile.life_state is not LifeState.ALIVE:
            continue
        domain = _actor_domain(hostile, tile_ids)
        candidates = (
            tuple(tile_ids - {actor_tile_id}) if domain is None else tuple(domain)
        )
        statuses = tuple(
            _line_status(state, actor_tile_id, tile_id) for tile_id in candidates
        )
        if (
            domain is not None
            and statuses
            and all(status is _LineStatus.CLEAR for status in statuses)
        ):
            minimum += 1
        if any(status is not _LineStatus.BLOCKED for status in statuses):
            maximum += 1
    if minimum == maximum:
        return MetricRange.exact(minimum)
    return MetricRange(minimum, maximum)


def _elevation_contact_range(
    state: TacticalState,
    actor_tile_id: str,
    *,
    actor_higher: bool,
) -> MetricRange:
    tile_by_id = {tile.tile_id: tile for tile in state.tiles}
    tile_ids = frozenset(tile_by_id)
    actor_tile = tile_by_id[actor_tile_id]
    minimum = 0
    maximum = 0
    for hostile in state.combatants:
        if hostile.relation is not Relation.HOSTILE:
            continue
        if hostile.life_state is not LifeState.ALIVE:
            continue
        domain = _actor_domain(hostile, tile_ids)
        candidates = tile_ids if domain is None else domain
        matches = []
        for tile_id in candidates:
            tile = tile_by_id[tile_id]
            elevation_matches = (
                actor_tile.elevation > tile.elevation
                if actor_higher
                else actor_tile.elevation < tile.elevation
            )
            matches.append(
                _adjacent(tile_by_id, actor_tile_id, tile_id) and elevation_matches
            )
        if domain is not None and matches and all(matches):
            minimum += 1
        if any(matches):
            maximum += 1
    if minimum == maximum:
        return MetricRange.exact(minimum)
    return MetricRange(minimum, maximum)


def _friendly_combatants(state: TacticalState) -> tuple[Combatant, ...]:
    return tuple(
        actor
        for actor in state.combatants
        if actor.actor_id != state.decision.active_actor_id
        and actor.relation in (Relation.PLAYER, Relation.ALLY)
        and actor.life_state is LifeState.ALIVE
    )


def _hostile_combatants(state: TacticalState) -> tuple[Combatant, ...]:
    return tuple(
        actor
        for actor in state.combatants
        if actor.relation is Relation.HOSTILE and actor.life_state is LifeState.ALIVE
    )


def _screen_pair_sets(
    state: TacticalState,
    actor_tile_id: str,
) -> tuple[frozenset[tuple[str, str]], frozenset[tuple[str, str]]]:
    tile_by_id = {tile.tile_id: tile for tile in state.tiles}
    tile_ids = frozenset(tile_by_id)
    actor_coordinate = tile_by_id[actor_tile_id].coordinate
    definite: set[tuple[str, str]] = set()
    possible: set[tuple[str, str]] = set()
    for ally in _friendly_combatants(state):
        ally_domain = _actor_domain(ally, tile_ids)
        ally_tiles = tile_ids if ally_domain is None else ally_domain
        for hostile in _hostile_combatants(state):
            hostile_domain = _actor_domain(hostile, tile_ids)
            hostile_tiles = tile_ids if hostile_domain is None else hostile_domain
            outcomes = []
            for ally_tile_id in ally_tiles:
                ally_coordinate = tile_by_id[ally_tile_id].coordinate
                for hostile_tile_id in hostile_tiles:
                    hostile_coordinate = tile_by_id[hostile_tile_id].coordinate
                    outcomes.append(
                        _adjacent(tile_by_id, actor_tile_id, ally_tile_id)
                        and _adjacent(
                            tile_by_id,
                            actor_tile_id,
                            hostile_tile_id,
                        )
                        and ally_coordinate.q + hostile_coordinate.q
                        == 2 * actor_coordinate.q
                        and ally_coordinate.r + hostile_coordinate.r
                        == 2 * actor_coordinate.r
                    )
            pair = (ally.actor_id, hostile.actor_id)
            if any(outcomes):
                possible.add(pair)
            if (
                ally_domain is not None
                and hostile_domain is not None
                and outcomes
                and all(outcomes)
            ):
                definite.add(pair)
    return frozenset(definite), frozenset(possible)


def _flanked_hostiles(state: TacticalState, actor_tile_id: str) -> MetricRange:
    tile_by_id = {tile.tile_id: tile for tile in state.tiles}
    tile_ids = frozenset(tile_by_id)
    allies = _friendly_combatants(state)
    minimum = 0
    maximum = 0
    for hostile in _hostile_combatants(state):
        hostile_domain = _actor_domain(hostile, tile_ids)
        hostile_tiles = tile_ids if hostile_domain is None else hostile_domain
        possible_for_hostile = False
        definite_for_hostile = hostile_domain is not None and bool(hostile_tiles)
        for hostile_tile_id in hostile_tiles:
            if not _adjacent(tile_by_id, actor_tile_id, hostile_tile_id):
                definite_for_hostile = False
                continue
            possible_support = False
            definite_support = False
            for ally in allies:
                ally_domain = _actor_domain(ally, tile_ids)
                ally_tiles = tile_ids if ally_domain is None else ally_domain
                adjacency = tuple(
                    _adjacent(tile_by_id, hostile_tile_id, ally_tile_id)
                    for ally_tile_id in ally_tiles
                )
                possible_support = possible_support or any(adjacency)
                definite_support = definite_support or (
                    ally_domain is not None and bool(adjacency) and all(adjacency)
                )
            possible_for_hostile = possible_for_hostile or possible_support
            definite_for_hostile = definite_for_hostile and definite_support
        maximum += int(possible_for_hostile)
        minimum += int(definite_for_hostile)
    if minimum == maximum:
        return MetricRange.exact(minimum)
    return MetricRange(minimum, maximum)


def _open_adjacent_tiles(
    state: TacticalState,
    actor: Combatant,
    actor_tile_id: str,
) -> MetricRange:
    tile_by_id = {tile.tile_id: tile for tile in state.tiles}
    tile_ids = frozenset(tile_by_id)
    other_domains = tuple(
        _actor_domain(other, tile_ids)
        for other in state.combatants
        if other.actor_id != actor.actor_id and other.life_state is LifeState.ALIVE
    )
    minimum = 0
    maximum = 0
    for neighbor_id in tile_by_id[actor_tile_id].neighbors:
        if neighbor_id is None:
            continue
        tile = tile_by_id[neighbor_id]
        traversable_minimum, traversable_maximum = _bool_bounds(tile.traversable)
        blocking_minimum, blocking_maximum = _bool_bounds(tile.blocking)
        definitely_occupied = any(
            domain == frozenset((neighbor_id,))
            for domain in other_domains
            if domain is not None
        )
        possibly_occupied = any(
            domain is None or neighbor_id in domain for domain in other_domains
        )
        definitely_open = (
            traversable_minimum and not blocking_maximum and not possibly_occupied
        )
        possibly_open = (
            traversable_maximum and not blocking_minimum and not definitely_occupied
        )
        minimum += int(definitely_open)
        maximum += int(possibly_open)
    if minimum == maximum:
        return MetricRange.exact(minimum)
    return MetricRange(minimum, maximum)


def _post_actor_tile(actor: Combatant, action: ActionAffordance) -> str:
    position = actor.position
    if position.representation is not Representation.EXACT:
        _unsupported(action, "post-action actor position must be exact")
    if not isinstance(position.value, str):
        _unsupported(action, "post-action actor position must be a tile ID")
    return position.value


def _attack_post_actor(
    state: TacticalState,
    action: ActionAffordance,
    outcome: AttackOutcome,
) -> Combatant:
    actor = next(
        combatant
        for combatant in state.combatants
        if combatant.actor_id == action.actor_id
    )
    if outcome.branches:
        branch = outcome.branches[0]
    elif outcome.epistemic_scenarios:
        branch = outcome.epistemic_scenarios[0].branches[0]
    else:
        _invalid(action, "attack outcome has no branches")
    if branch.actor_action_points is None or branch.actor_fatigue is None:
        _invalid(action, "attack outcome lacks post-action actor resources")
    return replace(
        actor,
        resources=replace(
            actor.resources,
            action_points=KnownValue.exact(branch.actor_action_points),
            fatigue=KnownValue.exact(branch.actor_fatigue),
        ),
    )


def _posture_branches(
    state: TacticalState,
    action: ActionAffordance,
    attack: AttackOutcome | None,
    transition: TransitionOutcome | None,
) -> tuple[_PostureBranch, ...]:
    if transition is not None:
        surviving = tuple(
            _PostureBranch(branch.probability, branch.actor)
            for branch in transition.branches
            if branch.actor.life_state is LifeState.ALIVE
        )
        if not surviving:
            return ()
        total_probability = sum(branch.probability for branch in surviving)
        return tuple(
            _PostureBranch(
                branch.probability / total_probability,
                branch.actor,
            )
            for branch in surviving
        )
    if attack is not None:
        return (_PostureBranch(1.0, _attack_post_actor(state, action, attack)),)
    _invalid(action, "tactical features require a candidate outcome")


def _posture_metric(
    branches: tuple[_PostureBranch, ...],
    measure: Callable[[Combatant], MetricRange],
) -> MetricRange:
    return _weighted_range(
        (branch.probability, measure(branch.actor)) for branch in branches
    )


def _movement_completion(
    action: ActionAffordance,
    transition: TransitionOutcome | None,
) -> MetricRange:
    if action.kind is not ActionKind.MOVE_TO:
        return MetricRange.exact(1)
    if transition is None:
        return MetricRange.exact(0)
    probability = sum(
        branch.probability for branch in transition.branches if branch.completed
    )
    return MetricRange.exact(probability)


def _cost(action: ActionAffordance, name: str) -> int:
    cost = getattr(action, name)
    if cost is None:
        _invalid(action, f"canonical action lacks {name}")
    return cost.value


def _template_id(action: ActionAffordance) -> str | None:
    if action.kind in (ActionKind.WAIT, ActionKind.END_TURN):
        return None
    identity = action.kind.value
    if action.skill_id is not None:
        identity += f":{action.skill_id}"
    if action.mode_variant is not None:
        identity += f":{action.mode_variant}"
    return (
        f"{identity}|ap={_cost(action, 'ap_cost')}"
        f"|fat={_cost(action, 'fatigue_cost')}"
        f"|ammo={_cost(action, 'ammo_cost')}"
        f"|charge={_cost(action, 'charge_cost')}"
    )


def _templates(
    state: TacticalState,
) -> tuple[tuple[str, ActionAffordance], ...]:
    by_id: dict[str, ActionAffordance] = {}
    for action in state.action_affordances.actions:
        template_id = _template_id(action)
        if template_id is not None:
            by_id.setdefault(template_id, action)
    return tuple(sorted(by_id.items()))


def _future_capacity(
    state: TacticalState,
    action: ActionAffordance,
    branches: tuple[_PostureBranch, ...],
) -> FutureCapacityFeatures:
    templates = _templates(state)
    template_ids = tuple(template_id for template_id, _ in templates)

    def feasible(actor: Combatant) -> MetricRange:
        action_points = _exact_int(
            actor.resources.action_points,
            "post-action AP",
            action,
        )
        fatigue = _exact_int(
            actor.resources.fatigue,
            "post-action fatigue",
            action,
        )
        fatigue_capacity = _exact_int(
            actor.resources.fatigue_capacity,
            "fatigue capacity",
            action,
        )
        count = sum(
            1
            for _, template in templates
            if action_points >= _cost(template, "ap_cost")
            and fatigue + _cost(template, "fatigue_cost") <= fatigue_capacity
        )
        return MetricRange.exact(count)

    feasible_range = _posture_metric(branches, feasible)
    locked_range = MetricRange(
        len(templates) - feasible_range.maximum,
        len(templates) - feasible_range.minimum,
        (
            len(templates) - feasible_range.expected
            if feasible_range.expected is not None
            else None
        ),
    )
    return FutureCapacityFeatures(
        template_ids,
        len(templates),
        feasible_range,
        locked_range,
    )


def _resources(
    action: ActionAffordance,
    branches: tuple[_PostureBranch, ...],
) -> ResourceFeatures:
    def action_points(actor: Combatant) -> MetricRange:
        return MetricRange.exact(
            _exact_int(
                actor.resources.action_points,
                "post-action AP",
                action,
            )
        )

    def fatigue(actor: Combatant) -> MetricRange:
        return MetricRange.exact(
            _exact_int(
                actor.resources.fatigue,
                "post-action fatigue",
                action,
            )
        )

    def fatigue_headroom(actor: Combatant) -> MetricRange:
        current = _exact_int(
            actor.resources.fatigue,
            "post-action fatigue",
            action,
        )
        capacity = _exact_int(
            actor.resources.fatigue_capacity,
            "fatigue capacity",
            action,
        )
        return MetricRange.exact(capacity - current)

    return ResourceFeatures(
        _posture_metric(branches, action_points),
        _posture_metric(branches, fatigue),
        _posture_metric(branches, fatigue_headroom),
        _cost(action, "ap_cost"),
        _cost(action, "fatigue_cost"),
        _cost(action, "ammo_cost"),
        _cost(action, "charge_cost"),
        _cost(action, "item_action_cost"),
    )


def _tempo(
    state: TacticalState,
    transition: TransitionOutcome | None,
) -> TempoFeatures:
    known_not_done = sum(
        1
        for entry in state.turn_state.entries
        if entry.done.representation is Representation.EXACT
        and entry.done.value is False
    )
    if transition is None:
        return TempoFeatures(
            MetricRange.exact(int(state.decision.actor_has_waited)),
            MetricRange.exact(int(state.decision.actor_may_wait)),
            MetricRange.exact(0),
            known_not_done,
        )

    waited = []
    may_wait = []
    ended = []
    for branch in transition.branches:
        actor_has_waited = (
            state.decision.actor_has_waited
            if branch.actor_has_waited is None
            else branch.actor_has_waited
        )
        actor_may_wait = (
            state.decision.actor_may_wait
            if branch.actor_may_wait is None
            else branch.actor_may_wait
        )
        waited.append((branch.probability, MetricRange.exact(int(actor_has_waited))))
        may_wait.append((branch.probability, MetricRange.exact(int(actor_may_wait))))
        ended.append((branch.probability, MetricRange.exact(int(branch.turn_ended))))
    return TempoFeatures(
        _weighted_range(waited),
        _weighted_range(may_wait),
        _weighted_range(ended),
        known_not_done,
    )


def _formation_features(
    state: TacticalState,
    action: ActionAffordance,
    branches: tuple[_PostureBranch, ...],
    current_tile_id: str,
) -> FormationFeatures:
    zero = MetricRange.exact(0)
    pre_definite, pre_possible = _screen_pair_sets(state, current_tile_id)
    direct_ranges = []
    lost_ranges = []
    created_ranges = []
    exposed_allies: set[str] = set()
    newly_screened_allies: set[str] = set()

    for branch in branches:
        post_tile_id = _post_actor_tile(branch.actor, action)
        post_definite, post_possible = _screen_pair_sets(state, post_tile_id)
        direct_ranges.append(
            (
                branch.probability,
                MetricRange(
                    len(post_definite),
                    len(post_possible),
                    (
                        float(len(post_definite))
                        if post_definite == post_possible
                        else None
                    ),
                ),
            )
        )
        if action.kind is not ActionKind.MOVE_TO:
            continue
        if post_tile_id == current_tile_id:
            lost_ranges.append((branch.probability, zero))
            created_ranges.append((branch.probability, zero))
            continue
        definitely_lost = pre_definite - post_possible
        possibly_lost = pre_possible - post_definite
        definitely_created = post_definite - pre_possible
        possibly_created = post_possible - pre_definite
        exposed_allies.update(ally_id for ally_id, _ in possibly_lost)
        newly_screened_allies.update(ally_id for ally_id, _ in possibly_created)
        lost_ranges.append(
            (
                branch.probability,
                MetricRange(
                    len(definitely_lost),
                    len(possibly_lost),
                    (
                        float(len(definitely_lost))
                        if definitely_lost == possibly_lost
                        else None
                    ),
                ),
            )
        )
        created_ranges.append(
            (
                branch.probability,
                MetricRange(
                    len(definitely_created),
                    len(possibly_created),
                    (
                        float(len(definitely_created))
                        if definitely_created == possibly_created
                        else None
                    ),
                ),
            )
        )

    adjacent_players = _posture_metric(
        branches,
        lambda actor: _relation_adjacency_range(
            state,
            _post_actor_tile(actor, action),
            Relation.PLAYER,
        ),
    )
    adjacent_allies = _posture_metric(
        branches,
        lambda actor: _relation_adjacency_range(
            state,
            _post_actor_tile(actor, action),
            Relation.ALLY,
        ),
    )
    expected = None
    if adjacent_players.expected is not None and adjacent_allies.expected is not None:
        expected = adjacent_players.expected + adjacent_allies.expected
    friendly_adjacency = MetricRange(
        adjacent_players.minimum + adjacent_allies.minimum,
        adjacent_players.maximum + adjacent_allies.maximum,
        expected,
    )
    return FormationFeatures(
        friendly_adjacency,
        _weighted_range(direct_ranges) if direct_ranges else zero,
        _weighted_range(lost_ranges) if lost_ranges else zero,
        _weighted_range(created_ranges) if created_ranges else zero,
        tuple(sorted(exposed_allies)),
        tuple(sorted(newly_screened_allies)),
    )


def _build_features(
    state: TacticalState,
    action: ActionAffordance,
    attack: AttackOutcome | None,
    transition: TransitionOutcome | None,
) -> TacticalFeatures:
    branches = _posture_branches(state, action, attack, transition)
    current_actor = next(
        actor for actor in state.combatants if actor.actor_id == action.actor_id
    )
    current_tile_id = _post_actor_tile(current_actor, action)
    tile_by_id = {tile.tile_id: tile for tile in state.tiles}
    current_elevation = tile_by_id[current_tile_id].elevation

    adjacent_hostiles = _posture_metric(
        branches,
        lambda actor: _relation_adjacency_range(
            state,
            _post_actor_tile(actor, action),
            Relation.HOSTILE,
        ),
    )
    if adjacent_hostiles.maximum == 0:
        hostile_zoc = MetricRange.exact(0)
    else:
        hostile_zoc = MetricRange(0, adjacent_hostiles.maximum)

    position = PositionFeatures(
        _posture_metric(
            branches,
            lambda actor: MetricRange.exact(
                tile_by_id[_post_actor_tile(actor, action)].elevation
            ),
        ),
        _posture_metric(
            branches,
            lambda actor: MetricRange.exact(
                tile_by_id[_post_actor_tile(actor, action)].elevation
                - current_elevation
            ),
        ),
        _posture_metric(
            branches,
            lambda actor: _elevation_contact_range(
                state,
                _post_actor_tile(actor, action),
                actor_higher=True,
            ),
        ),
        _posture_metric(
            branches,
            lambda actor: _elevation_contact_range(
                state,
                _post_actor_tile(actor, action),
                actor_higher=False,
            ),
        ),
    )
    threat = ThreatFeatures(
        adjacent_hostiles,
        hostile_zoc,
        _posture_metric(
            branches,
            lambda actor: _ranged_los_range(
                state,
                _post_actor_tile(actor, action),
            ),
        ),
    )
    control = ControlFeatures(
        _posture_metric(
            branches,
            lambda actor: _flanked_hostiles(
                state,
                _post_actor_tile(actor, action),
            ),
        )
    )
    mobility = MobilityFeatures(
        _posture_metric(
            branches,
            lambda actor: _open_adjacent_tiles(
                state,
                actor,
                _post_actor_tile(actor, action),
            ),
        ),
        _movement_completion(action, transition),
    )
    if attack is not None:
        outcome_model_version = attack.model_version
    elif transition is not None:
        outcome_model_version = transition.model_version
    else:
        _invalid(action, "tactical features require an outcome model version")

    return TacticalFeatures(
        action.action_id,
        MODEL_VERSION,
        outcome_model_version,
        _enemy_effect(attack),
        _friendly_harm(state, action, transition),
        threat,
        position,
        _formation_features(state, action, branches, current_tile_id),
        control,
        mobility,
        _resources(action, branches),
        _future_capacity(state, action, branches),
        _tempo(state, transition),
    )


def extract_candidate_features(
    authority: MechanicsAuthority,
    state: TacticalState,
    action: CandidateReference,
) -> Result[TacticalFeatures]:
    """Extract #20 raw features for one canonical current candidate."""

    candidate = resolve_current_candidate(authority, state, action)
    if candidate.value is None:
        return Result(candidate.status, problems=candidate.problems)

    canonical_state = candidate.value.state
    canonical_action = candidate.value.action
    attack: AttackOutcome | None = None
    transition: TransitionOutcome | None = None

    if "ordinary_attack" in candidate.value.structural_coverage.family_ids:
        attack_result = evaluate_ordinary_attack(
            authority,
            canonical_state,
            canonical_action.action_id,
        )
        if attack_result.value is None:
            return Result(attack_result.status, problems=attack_result.problems)
        attack = attack_result.value
    else:
        transition_result = evaluate_transition(
            authority,
            canonical_state,
            canonical_action.action_id,
        )
        if transition_result.value is None:
            return Result(
                transition_result.status,
                problems=transition_result.problems,
            )
        transition = transition_result.value

    try:
        features = _build_features(
            canonical_state,
            canonical_action,
            attack,
            transition,
        )
        return Result.success(features)
    except (EvaluationUnsupported, EvaluationInvalid) as exc:
        return evaluation_failure_result(exc)
