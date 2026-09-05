"""Raw tactical features for supported current candidates.

This module deliberately stops before #21 policy.  It turns canonical #40
candidate outcomes/transitions into deterministic, inspectable facts and bounded
spatial proxies.  It never generates a second command, infers an enemy action,
or replaces uncertain player-legal knowledge with debug truth.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import IntEnum
from typing import Callable, Iterable

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
from bb_agent.transitions import TransitionBranch, TransitionOutcome, evaluate_transition

MODEL_VERSION = "tactical-features.v1"


@dataclass(frozen=True, slots=True)
class MetricRange:
    """A raw metric with a robustness envelope and optional justified expectation.

    ``minimum``/``maximum`` are bounds across epistemic possibilities or immediate
    outcome branches. ``expected`` is present only when a probability model is
    justified for the whole represented domain.  No midpoint is invented for an
    unweighted SET/RANGE/UNKNOWN input.
    """

    minimum: float
    maximum: float
    expected: float | None = None

    def __post_init__(self) -> None:
        values = (self.minimum, self.maximum)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("feature bounds must be finite")
        if self.minimum > self.maximum:
            raise ValueError("feature minimum exceeds maximum")
        if self.expected is not None:
            if not math.isfinite(self.expected):
                raise ValueError("feature expectation must be finite")
            if self.expected < self.minimum - 1e-9 or self.expected > self.maximum + 1e-9:
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
        "direct hostile HP/armor effect and removal probability from the current command",
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
        "immediate AOO damage and any inferred enemy command or attack probability",
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
class _SpatialBranch:
    probability: float
    actor: Combatant


class _LineStatus(IntEnum):
    BLOCKED = 0
    UNCERTAIN = 1
    CLEAR = 2


def _invalid(action: ActionAffordance, message: str) -> None:
    raise EvaluationInvalid(
        message, path=f"action_affordances.{action.action_id}.features"
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


def _envelope(values: Iterable[float], *, expected: float | None = None) -> MetricRange:
    items = tuple(float(value) for value in values)
    if not items:
        return MetricRange.exact(0)
    return MetricRange(min(items), max(items), expected)


def _aggregate_weighted(
    values: Iterable[tuple[float, MetricRange]],
) -> MetricRange:
    items = tuple(values)
    if not items:
        return MetricRange.exact(0)
    minimum = min(metric.minimum for _, metric in items)
    maximum = max(metric.maximum for _, metric in items)
    total = sum(probability for probability, _ in items)
    expected = None
    if abs(total - 1.0) <= 1e-9 and all(
        metric.expected is not None for _, metric in items
    ):
        expected = sum(
            probability * metric.expected  # type: ignore[operator]
            for probability, metric in items
        )
    return MetricRange(minimum, maximum, expected)


def _aggregate_unweighted(values: Iterable[MetricRange]) -> MetricRange:
    items = tuple(values)
    if not items:
        return MetricRange.exact(0)
    minimum = min(metric.minimum for metric in items)
    maximum = max(metric.maximum for metric in items)
    if minimum == maximum and all(
        metric.expected == minimum for metric in items
    ):
        return MetricRange.exact(minimum)
    return MetricRange(minimum, maximum)


def _branch_expectation(
    branches: tuple[OutcomeBranch, ...], selector: Callable[[OutcomeBranch], float]
) -> float:
    return sum(branch.probability * selector(branch) for branch in branches)


def _attack_metric(
    outcome: AttackOutcome, selector: Callable[[OutcomeBranch], float]
) -> MetricRange:
    if outcome.epistemic_scenarios:
        return _envelope(
            _branch_expectation(scenario.branches, selector)
            for scenario in outcome.epistemic_scenarios
        )
    value = _branch_expectation(outcome.branches, selector)
    return MetricRange.exact(value)


def _enemy_effect(outcome: AttackOutcome | None) -> EnemyEffectFeatures:
    if outcome is None:
        zero = MetricRange.exact(0)
        return EnemyEffectFeatures(zero, zero, zero)
    return EnemyEffectFeatures(
        _attack_metric(outcome, lambda branch: float(branch.hp_damage)),
        _attack_metric(outcome, lambda branch: float(branch.armor_damage)),
        _attack_metric(outcome, lambda branch: 1.0 if branch.killed else 0.0),
    )


def _friendly_harm(
    state: TacticalState,
    action: ActionAffordance,
    outcome: TransitionOutcome | None,
) -> FriendlyHarmFeatures:
    zero = MetricRange.exact(0)
    if outcome is None or not action.contingent_reactions:
        return FriendlyHarmFeatures(zero, zero, zero, zero, ())
    actor = next(
        item for item in state.combatants if item.actor_id == action.actor_id
    )
    starting_hp = _exact_int(actor.resources.hit_points, "actor HP", action)
    hp_damage = []
    death_probability = 0.0
    interrupted_probability = 0.0
    for branch in outcome.branches:
        ending_hp = _exact_int(branch.actor.resources.hit_points, "post-action HP", action)
        hp_damage.append((branch.probability, max(0, starting_hp - ending_hp)))
        if branch.actor.life_state is not LifeState.ALIVE:
            death_probability += branch.probability
        if branch.interrupted:
            interrupted_probability += branch.probability
    expected_damage = sum(probability * damage for probability, damage in hp_damage)
    damage_values = [damage for _, damage in hp_damage]
    return FriendlyHarmFeatures(
        MetricRange(min(damage_values), max(damage_values), expected_damage),
        zero,
        MetricRange.exact(death_probability),
        MetricRange.exact(interrupted_probability),
        tuple(sorted({item.reacting_actor_id for item in action.contingent_reactions})),
    )


def _actor_domain(actor: Combatant, tile_ids: frozenset[str]) -> frozenset[str] | None:
    value = actor.position
    if value.representation is Representation.EXACT:
        if isinstance(value.value, str) and value.value in tile_ids:
            return frozenset((value.value,))
        return None
    if value.representation is Representation.SET:
        if all(isinstance(item, str) and item in tile_ids for item in value.candidates):
            return frozenset(value.candidates)
        return None
    if value.representation is Representation.DISTRIBUTION:
        if all(
            isinstance(item, str) and item in tile_ids
            for item, _ in value.distribution
        ):
            return frozenset(item for item, _ in value.distribution)
    return None


def _adjacent(tile_by_id: dict[str, Tile], left: str, right: str) -> bool:
    tile = tile_by_id.get(left)
    return tile is not None and right in tile.neighbors


def _relation_adjacency_range(
    state: TacticalState,
    actor_tile_id: str,
    relation: Relation,
) -> MetricRange:
    tile_by_id = {tile.tile_id: tile for tile in state.tiles}
    tile_ids = frozenset(tile_by_id)
    actor_tile = tile_by_id[actor_tile_id]
    has_neighbor = any(neighbor is not None for neighbor in actor_tile.neighbors)
    minimum = maximum = 0
    for other in state.combatants:
        if other.relation is not relation or other.life_state is not LifeState.ALIVE:
            continue
        domain = _actor_domain(other, tile_ids)
        if domain is None:
            maximum += 1 if has_neighbor else 0
            continue
        adjacent = tuple(_adjacent(tile_by_id, actor_tile_id, tile) for tile in domain)
        if adjacent and all(adjacent):
            minimum += 1
        if any(adjacent):
            maximum += 1
    return MetricRange.exact(minimum) if minimum == maximum else MetricRange(minimum, maximum)


def _bool_bounds(value: KnownValue) -> tuple[bool, bool]:
    if value.representation is Representation.EXACT and isinstance(value.value, bool):
        return value.value, value.value
    if value.representation is Representation.SET and value.candidates and all(
        isinstance(item, bool) for item in value.candidates
    ):
        return all(value.candidates), any(value.candidates)
    if value.representation is Representation.DISTRIBUTION and value.distribution and all(
        isinstance(item, bool) for item, _ in value.distribution
    ):
        candidates = tuple(item for item, _ in value.distribution)
        return all(candidates), any(candidates)
    return False, True


def _cube_round(q: float, r: float) -> HexCoord:
    x, z, y = q, r, -q - r
    rx, ry, rz = round(x), round(y), round(z)
    dx, dy, dz = abs(rx - x), abs(ry - y), abs(rz - z)
    if dx > dy and dx > dz:
        rx = -ry - rz
    elif dy > dz:
        ry = -rx - rz
    else:
        rz = -rx - ry
    return HexCoord(int(rx), int(rz))


def _hex_line(
    start: HexCoord, end: HexCoord, coordinate_to_tile: dict[HexCoord, str]
) -> tuple[str | None, ...]:
    distance = start.distance_to(end)
    if distance == 0:
        return ()
    # A tiny deterministic nudge resolves exact vertex ties consistently without
    # changing the canonical coordinate contract.
    aq, ar = start.q + 1e-7, start.r + 2e-7
    bq, br = end.q + 1e-7, end.r + 2e-7
    result = []
    for step in range(1, distance):
        fraction = step / distance
        coord = _cube_round(aq + (bq - aq) * fraction, ar + (br - ar) * fraction)
        result.append(coordinate_to_tile.get(coord))
    return tuple(result)


def _line_status(state: TacticalState, actor_tile_id: str, hostile_tile_id: str) -> _LineStatus:
    tile_by_id = {tile.tile_id: tile for tile in state.tiles}
    actor_tile = tile_by_id[actor_tile_id]
    hostile_tile = tile_by_id[hostile_tile_id]
    if actor_tile.coordinate.distance_to(hostile_tile.coordinate) < 2:
        return _LineStatus.BLOCKED
    coordinate_to_tile = {tile.coordinate: tile.tile_id for tile in state.tiles}
    uncertain = False
    for tile_id in _hex_line(actor_tile.coordinate, hostile_tile.coordinate, coordinate_to_tile):
        if tile_id is None:
            uncertain = True
            continue
        blocked_min, blocked_max = _bool_bounds(tile_by_id[tile_id].blocks_line_of_sight)
        if blocked_min:
            return _LineStatus.BLOCKED
        if blocked_max:
            uncertain = True
    return _LineStatus.UNCERTAIN if uncertain else _LineStatus.CLEAR


def _ranged_los_range(state: TacticalState, actor_tile_id: str) -> MetricRange:
    tile_by_id = {tile.tile_id: tile for tile in state.tiles}
    tile_ids = frozenset(tile_by_id)
    minimum = maximum = 0
    for hostile in state.combatants:
        if hostile.relation is not Relation.HOSTILE or hostile.life_state is not LifeState.ALIVE:
            continue
        domain = _actor_domain(hostile, tile_ids)
        if domain is None:
            statuses = tuple(
                _line_status(state, actor_tile_id, tile_id)
                for tile_id in tile_ids
                if tile_id != actor_tile_id
            )
            if any(status is not _LineStatus.BLOCKED for status in statuses):
                maximum += 1
            continue
        statuses = tuple(_line_status(state, actor_tile_id, tile_id) for tile_id in domain)
        if statuses and all(status is _LineStatus.CLEAR for status in statuses):
            minimum += 1
        if any(status is not _LineStatus.BLOCKED for status in statuses):
            maximum += 1
    return MetricRange.exact(minimum) if minimum == maximum else MetricRange(minimum, maximum)


def _elevation_contact_range(
    state: TacticalState, actor_tile_id: str, *, actor_higher: bool
) -> MetricRange:
    tile_by_id = {tile.tile_id: tile for tile in state.tiles}
    tile_ids = frozenset(tile_by_id)
    actor_tile = tile_by_id[actor_tile_id]
    minimum = maximum = 0
    for hostile in state.combatants:
        if hostile.relation is not Relation.HOSTILE or hostile.life_state is not LifeState.ALIVE:
            continue
        domain = _actor_domain(hostile, tile_ids)
        candidates = tile_ids if domain is None else domain
        matches = []
        for tile_id in candidates:
            tile = tile_by_id[tile_id]
            elevation_match = (
                actor_tile.elevation > tile.elevation
                if actor_higher
                else actor_tile.elevation < tile.elevation
            )
            matches.append(_adjacent(tile_by_id, actor_tile_id, tile_id) and elevation_match)
        if domain is not None and matches and all(matches):
            minimum += 1
        if any(matches):
            maximum += 1
    return MetricRange.exact(minimum) if minimum == maximum else MetricRange(minimum, maximum)


def _screen_pair_sets(
    state: TacticalState, actor_tile_id: str
) -> tuple[frozenset[tuple[str, str]], frozenset[tuple[str, str]]]:
    tile_by_id = {tile.tile_id: tile for tile in state.tiles}
    tile_ids = frozenset(tile_by_id)
    actor_coord = tile_by_id[actor_tile_id].coordinate
    definite: set[tuple[str, str]] = set()
    possible: set[tuple[str, str]] = set()
    allies = tuple(
        actor
        for actor in state.combatants
        if actor.relation in (Relation.PLAYER, Relation.ALLY)
        and actor.actor_id != state.decision.active_actor_id
        and actor.life_state is LifeState.ALIVE
    )
    hostiles = tuple(
        actor
        for actor in state.combatants
        if actor.relation is Relation.HOSTILE and actor.life_state is LifeState.ALIVE
    )
    for ally in allies:
        ally_domain = _actor_domain(ally, tile_ids)
        ally_tiles = tile_ids if ally_domain is None else ally_domain
        for hostile in hostiles:
            hostile_domain = _actor_domain(hostile, tile_ids)
            hostile_tiles = tile_ids if hostile_domain is None else hostile_domain
            results = []
            for ally_tile_id in ally_tiles:
                ally_coord = tile_by_id[ally_tile_id].coordinate
                for hostile_tile_id in hostile_tiles:
                    hostile_coord = tile_by_id[hostile_tile_id].coordinate
                    results.append(
                        _adjacent(tile_by_id, actor_tile_id, ally_tile_id)
                        and _adjacent(tile_by_id, actor_tile_id, hostile_tile_id)
                        and ally_coord.q + hostile_coord.q == 2 * actor_coord.q
                        and ally_coord.r + hostile_coord.r == 2 * actor_coord.r
                    )
            pair = (ally.actor_id, hostile.actor_id)
            if any(results):
                possible.add(pair)
            if (
                ally_domain is not None
                and hostile_domain is not None
                and results
                and all(results)
            ):
                definite.add(pair)
    return frozenset(definite), frozenset(possible)


def _flanked_hostiles(state: TacticalState, actor_tile_id: str) -> MetricRange:
    tile_by_id = {tile.tile_id: tile for tile in state.tiles}
    tile_ids = frozenset(tile_by_id)
    allies = tuple(
        actor
        for actor in state.combatants
        if actor.relation in (Relation.PLAYER, Relation.ALLY)
        and actor.actor_id != state.decision.active_actor_id
        and actor.life_state is LifeState.ALIVE
    )
    minimum = maximum = 0
    for hostile in state.combatants:
        if hostile.relation is not Relation.HOSTILE or hostile.life_state is not LifeState.ALIVE:
            continue
        hostile_domain = _actor_domain(hostile, tile_ids)
        hostile_tiles = tile_ids if hostile_domain is None else hostile_domain
        per_hostile = []
        for hostile_tile_id in hostile_tiles:
            if not _adjacent(tile_by_id, actor_tile_id, hostile_tile_id):
                per_hostile.append(False)
                continue
            ally_support = False
            for ally in allies:
                ally_domain = _actor_domain(ally, tile_ids)
                ally_tiles = tile_ids if ally_domain is None else ally_domain
                if any(
                    _adjacent(tile_by_id, hostile_tile_id, ally_tile_id)
                    for ally_tile_id in ally_tiles
                ):
                    ally_support = True
                    break
            per_hostile.append(ally_support)
        if any(per_hostile):
            maximum += 1
        if hostile_domain is not None and per_hostile and all(per_hostile):
            # The lower bound is intentionally conservative for uncertain allies.
            supported_everywhere = True
            for hostile_tile_id in hostile_tiles:
                if not _adjacent(tile_by_id, actor_tile_id, hostile_tile_id):
                    supported_everywhere = False
                    break
                if not any(
                    (domain := _actor_domain(ally, tile_ids)) is not None
                    and domain
                    and all(
                        _adjacent(tile_by_id, hostile_tile_id, ally_tile_id)
                        for ally_tile_id in domain
                    )
                    for ally in allies
                ):
                    supported_everywhere = False
                    break
            if supported_everywhere:
                minimum += 1
    return MetricRange.exact(minimum) if minimum == maximum else MetricRange(minimum, maximum)


def _open_adjacent_tiles(
    state: TacticalState, actor: Combatant, actor_tile_id: str
) -> MetricRange:
    tile_by_id = {tile.tile_id: tile for tile in state.tiles}
    tile_ids = frozenset(tile_by_id)
    other_domains = tuple(
        _actor_domain(other, tile_ids)
        for other in state.combatants
        if other.actor_id != actor.actor_id and other.life_state is LifeState.ALIVE
    )
    minimum = maximum = 0
    for neighbor_id in tile_by_id[actor_tile_id].neighbors:
        if neighbor_id is None:
            continue
        tile = tile_by_id[neighbor_id]
        traversable_min, traversable_max = _bool_bounds(tile.traversable)
        blocking_min, blocking_max = _bool_bounds(tile.blocking)
        definitely_occupied = any(
            domain is not None and domain == frozenset((neighbor_id,))
            for domain in other_domains
        )
        possibly_occupied = any(
            domain is None or neighbor_id in domain for domain in other_domains
        )
        definitely_open = (
            traversable_min and not blocking_max and not possibly_occupied
        )
        possibly_open = (
            traversable_max and not blocking_min and not definitely_occupied
        )
        minimum += int(definitely_open)
        maximum += int(possibly_open)
    return MetricRange.exact(minimum) if minimum == maximum else MetricRange(minimum, maximum)


def _post_actor_tile(actor: Combatant, action: ActionAffordance) -> str:
    if actor.position.representation is not Representation.EXACT or not isinstance(
        actor.position.value, str
    ):
        _unsupported(action, "post-action actor position must be exact")
    return actor.position.value


def _spatial_branches(
    state: TacticalState,
    action: ActionAffordance,
    attack: AttackOutcome | None,
    transition: TransitionOutcome | None,
) -> tuple[_SpatialBranch, ...]:
    current_actor = next(
        actor for actor in state.combatants if actor.actor_id == action.actor_id
    )
    if transition is not None:
        living = tuple(
            _SpatialBranch(branch.probability, branch.actor)
            for branch in transition.branches
            if branch.actor.life_state is LifeState.ALIVE
        )
        if not living:
            return ()
        total = sum(branch.probability for branch in living)
        return tuple(
            _SpatialBranch(branch.probability / total, branch.actor) for branch in living
        )
    if attack is not None:
        branch = attack.branches[0] if attack.branches else attack.epistemic_scenarios[0].branches[0]
        if branch.actor_action_points is None or branch.actor_fatigue is None:
            _invalid(action, "attack outcome lacks post-action actor resources")
        actor = replace(
            current_actor,
            resources=replace(
                current_actor.resources,
                action_points=KnownValue.exact(branch.actor_action_points),
                fatigue=KnownValue.exact(branch.actor_fatigue),
            ),
        )
        return (_SpatialBranch(1.0, actor),)
    _invalid(action, "tactical features require a candidate outcome")


def _spatial_metric(
    branches: tuple[_SpatialBranch, ...],
    measure: Callable[[Combatant], MetricRange],
) -> MetricRange:
    if not branches:
        return MetricRange.exact(0)
    return _aggregate_weighted(
        (branch.probability, measure(branch.actor)) for branch in branches
    )


def _movement_completion(action: ActionAffordance, transition: TransitionOutcome | None) -> MetricRange:
    if action.kind is not ActionKind.MOVE_TO:
        return MetricRange.exact(1)
    if transition is None:
        return MetricRange.exact(0)
    return MetricRange.exact(
        sum(branch.probability for branch in transition.branches if branch.completed)
    )


def _cost(action: ActionAffordance, name: str) -> int:
    value = getattr(action, name)
    if value is None:
        _invalid(action, f"canonical action lacks {name}")
    return value.value


def _template_id(action: ActionAffordance) -> str | None:
    if action.kind in (ActionKind.WAIT, ActionKind.END_TURN):
        return None
    identity = action.kind.value
    if action.skill_id is not None:
        identity += f":{action.skill_id}"
    elif action.kind is ActionKind.EQUIP_ITEM:
        identity += ":equip"
    return (
        f"{identity}|ap={_cost(action, 'ap_cost')}|fat={_cost(action, 'fatigue_cost')}"
        f"|ammo={_cost(action, 'ammo_cost')}|charge={_cost(action, 'charge_cost')}"
    )


def _templates(state: TacticalState) -> tuple[tuple[str, ActionAffordance], ...]:
    by_id: dict[str, ActionAffordance] = {}
    for action in state.action_affordances.actions:
        template_id = _template_id(action)
        if template_id is not None:
            by_id.setdefault(template_id, action)
    return tuple(sorted(by_id.items()))


def _future_capacity(
    state: TacticalState,
    action: ActionAffordance,
    branches: tuple[_SpatialBranch, ...],
) -> FutureCapacityFeatures:
    templates = _templates(state)
    template_ids = tuple(template_id for template_id, _ in templates)

    def feasible(actor: Combatant) -> MetricRange:
        if actor.life_state is not LifeState.ALIVE:
            return MetricRange.exact(0)
        ap = _exact_int(actor.resources.action_points, "post-action AP", action)
        fatigue = _exact_int(actor.resources.fatigue, "post-action fatigue", action)
        capacity = _exact_int(actor.resources.fatigue_capacity, "fatigue capacity", action)
        count = sum(
            1
            for _, template in templates
            if ap >= _cost(template, "ap_cost")
            and fatigue + _cost(template, "fatigue_cost") <= capacity
        )
        return MetricRange.exact(count)

    feasible_range = _spatial_metric(branches, feasible)
    locked = MetricRange(
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
        locked,
    )


def _resources(
    state: TacticalState,
    action: ActionAffordance,
    branches: tuple[_SpatialBranch, ...],
) -> ResourceFeatures:
    def ap(actor: Combatant) -> MetricRange:
        return MetricRange.exact(
            _exact_int(actor.resources.action_points, "post-action AP", action)
        )

    def fatigue(actor: Combatant) -> MetricRange:
        return MetricRange.exact(
            _exact_int(actor.resources.fatigue, "post-action fatigue", action)
        )

    def headroom(actor: Combatant) -> MetricRange:
        current = _exact_int(actor.resources.fatigue, "post-action fatigue", action)
        capacity = _exact_int(actor.resources.fatigue_capacity, "fatigue capacity", action)
        return MetricRange.exact(capacity - current)

    return ResourceFeatures(
        _spatial_metric(branches, ap),
        _spatial_metric(branches, fatigue),
        _spatial_metric(branches, headroom),
        _cost(action, "ap_cost"),
        _cost(action, "fatigue_cost"),
        _cost(action, "ammo_cost"),
        _cost(action, "charge_cost"),
        _cost(action, "item_action_cost"),
    )


def _tempo(
    state: TacticalState,
    action: ActionAffordance,
    transition: TransitionOutcome | None,
) -> TempoFeatures:
    known_not_done = sum(
        1
        for entry in state.turn_state.entries
        if entry.done.representation is Representation.EXACT and entry.done.value is False
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
        waited.append(
            (
                branch.probability,
                MetricRange.exact(
                    int(
                        state.decision.actor_has_waited
                        if branch.actor_has_waited is None
                        else branch.actor_has_waited
                    )
                ),
            )
        )
        may_wait.append(
            (
                branch.probability,
                MetricRange.exact(
                    int(
                        state.decision.actor_may_wait
                        if branch.actor_may_wait is None
                        else branch.actor_may_wait
                    )
                ),
            )
        )
        ended.append((branch.probability, MetricRange.exact(int(branch.turn_ended))))
    return TempoFeatures(
        _aggregate_weighted(waited),
        _aggregate_weighted(may_wait),
        _aggregate_weighted(ended),
        known_not_done,
    )


def _build_features(
    state: TacticalState,
    action: ActionAffordance,
    attack: AttackOutcome | None,
    transition: TransitionOutcome | None,
) -> TacticalFeatures:
    branches = _spatial_branches(state, action, attack, transition)
    current_actor = next(
        actor for actor in state.combatants if actor.actor_id == action.actor_id
    )
    current_tile_id = _post_actor_tile(current_actor, action)
    tile_by_id = {tile.tile_id: tile for tile in state.tiles}
    current_elevation = tile_by_id[current_tile_id].elevation

    threat_adjacent = _spatial_metric(
        branches,
        lambda actor: _relation_adjacency_range(
            state, _post_actor_tile(actor, action), Relation.HOSTILE
        ),
    )
    # The canonical state has no general hostile ZOC-capability field.  Adjacency
    # is therefore an upper bound, never proof that an enemy can make an AOO.
    hostile_zoc = MetricRange(0, threat_adjacent.maximum)

    elevation = _spatial_metric(
        branches,
        lambda actor: MetricRange.exact(
            tile_by_id[_post_actor_tile(actor, action)].elevation
        ),
    )
    elevation_change = _spatial_metric(
        branches,
        lambda actor: MetricRange.exact(
            tile_by_id[_post_actor_tile(actor, action)].elevation - current_elevation
        ),
    )
    adjacent_allies = _spatial_metric(
        branches,
        lambda actor: _relation_adjacency_range(
            state, _post_actor_tile(actor, action), Relation.PLAYER
        ),
    )
    # Allied NPCs are a second friendly relation and are folded into support here.
    adjacent_npc_allies = _spatial_metric(
        branches,
        lambda actor: _relation_adjacency_range(
            state, _post_actor_tile(actor, action), Relation.ALLY
        ),
    )
    adjacent_allies = MetricRange(
        adjacent_allies.minimum + adjacent_npc_allies.minimum,
        adjacent_allies.maximum + adjacent_npc_allies.maximum,
        (
            adjacent_allies.expected + adjacent_npc_allies.expected
            if adjacent_allies.expected is not None
            and adjacent_npc_allies.expected is not None
            else None
        ),
    )

    pre_definite, pre_possible = _screen_pair_sets(state, current_tile_id)
    post_screen_ranges = []
    lost_ranges = []
    created_ranges = []
    exposed_allies: set[str] = set()
    screened_allies: set[str] = set()
    for branch in branches:
        post_tile_id = _post_actor_tile(branch.actor, action)
        post_definite, post_possible = _screen_pair_sets(state, post_tile_id)
        post_screen_ranges.append(
            (
                branch.probability,
                MetricRange(
                    len(post_definite),
                    len(post_possible),
                    float(len(post_definite)) if post_definite == post_possible else None,
                ),
            )
        )
        if action.kind is ActionKind.MOVE_TO:
            definitely_lost = pre_definite - post_possible
            possibly_lost = pre_possible - post_definite
            definitely_created = post_definite - pre_possible
            possibly_created = post_possible - pre_definite
            exposed_allies.update(ally for ally, _ in possibly_lost)
            screened_allies.update(ally for ally, _ in possibly_created)
            lost_ranges.append(
                (
                    branch.probability,
                    MetricRange(
                        len(definitely_lost),
                        len(possibly_lost),
                        float(len(definitely_lost))
                        if definitely_lost == possibly_lost
                        else None,
                    ),
                )
            )
            created_ranges.append(
                (
                    branch.probability,
                    MetricRange(
                        len(definitely_created),
                        len(possibly_created),
                        float(len(definitely_created))
                        if definitely_created == possibly_created
                        else None,
                    ),
                )
            )
    zero = MetricRange.exact(0)
    direct_screen = _aggregate_weighted(post_screen_ranges) if post_screen_ranges else zero
    lost_screen = _aggregate_weighted(lost_ranges) if lost_ranges else zero
    created_screen = _aggregate_weighted(created_ranges) if created_ranges else zero

    outcome_version = attack.model_version if attack is not None else transition.model_version  # type: ignore[union-attr]
    return TacticalFeatures(
        action.action_id,
        MODEL_VERSION,
        outcome_version,
        _enemy_effect(attack),
        _friendly_harm(state, action, transition),
        ThreatFeatures(
            threat_adjacent,
            hostile_zoc,
            _spatial_metric(
                branches,
                lambda actor: _ranged_los_range(state, _post_actor_tile(actor, action)),
            ),
        ),
        PositionFeatures(
            elevation,
            elevation_change,
            _spatial_metric(
                branches,
                lambda actor: _elevation_contact_range(
                    state, _post_actor_tile(actor, action), actor_higher=True
                ),
            ),
            _spatial_metric(
                branches,
                lambda actor: _elevation_contact_range(
                    state, _post_actor_tile(actor, action), actor_higher=False
                ),
            ),
        ),
        FormationFeatures(
            adjacent_allies,
            direct_screen,
            lost_screen,
            created_screen,
            tuple(sorted(exposed_allies)),
            tuple(sorted(screened_allies)),
        ),
        ControlFeatures(
            _spatial_metric(
                branches,
                lambda actor: _flanked_hostiles(state, _post_actor_tile(actor, action)),
            )
        ),
        MobilityFeatures(
            _spatial_metric(
                branches,
                lambda actor: _open_adjacent_tiles(
                    state, actor, _post_actor_tile(actor, action)
                ),
            ),
            _movement_completion(action, transition),
        ),
        _resources(state, action, branches),
        _future_capacity(state, action, branches),
        _tempo(state, action, transition),
    )


def extract_candidate_features(
    authority: MechanicsAuthority,
    state: TacticalState,
    action: CandidateReference,
) -> Result[TacticalFeatures]:
    """Extract #20 raw features for one canonical current candidate.

    A legacy ``ActionAffordance`` argument is only an identity reference because
    candidate resolution is delegated to the #40 boundary.  Unsupported mechanics,
    stale state, and concrete evaluation failures preserve the same result classes
    as the underlying outcome/transition evaluator.
    """

    candidate = resolve_current_candidate(authority, state, action)
    if candidate.value is None:
        return Result(candidate.status, problems=candidate.problems)
    canonical_state = candidate.value.state
    canonical_action = candidate.value.action

    attack: AttackOutcome | None = None
    transition: TransitionOutcome | None = None
    if "ordinary_attack" in candidate.value.structural_coverage.family_ids:
        evaluated = evaluate_ordinary_attack(
            authority, canonical_state, canonical_action.action_id
        )
        if evaluated.value is None:
            return Result(evaluated.status, problems=evaluated.problems)
        attack = evaluated.value
    else:
        evaluated_transition = evaluate_transition(
            authority, canonical_state, canonical_action.action_id
        )
        if evaluated_transition.value is None:
            return Result(
                evaluated_transition.status, problems=evaluated_transition.problems
            )
        transition = evaluated_transition.value

    try:
        return Result.success(
            _build_features(
                canonical_state, canonical_action, attack, transition
            )
        )
    except (EvaluationUnsupported, EvaluationInvalid) as exc:
        return evaluation_failure_result(exc)
