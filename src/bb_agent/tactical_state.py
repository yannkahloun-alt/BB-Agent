"""Versioned canonical tactical-state and current-action affordance contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, is_dataclass, replace
from enum import StrEnum
from types import UnionType
from typing import Any, Self, get_args, get_origin, get_type_hints

from bb_agent.serialization import JsonValue, canonical_sha256
from bb_agent.versions import CURRENT_VERSIONS


class InformationProfile(StrEnum):
    PLAYER_LEGAL = "player_legal"
    OMNISCIENT_DEBUG = "omniscient_debug"


class KnowledgeClass(StrEnum):
    EXACT_OBSERVED = "EXACT_OBSERVED"
    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    REMEMBERED = "REMEMBERED"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"
    DEBUG_GROUND_TRUTH = "DEBUG_GROUND_TRUTH"


class Representation(StrEnum):
    EXACT = "EXACT"
    RANGE = "RANGE"
    SET = "SET"
    DISTRIBUTION = "DISTRIBUTION"
    UNKNOWN = "UNKNOWN"


class Relation(StrEnum):
    PLAYER = "PLAYER"
    ALLY = "ALLY"
    HOSTILE = "HOSTILE"
    NEUTRAL = "NEUTRAL"


class LifeState(StrEnum):
    ALIVE = "ALIVE"
    DYING = "DYING"
    FLED = "FLED"
    REMOVED = "REMOVED"


class ActionKind(StrEnum):
    MOVE_TO = "MOVE_TO"
    USE_SKILL = "USE_SKILL"
    EQUIP_ITEM = "EQUIP_ITEM"
    WAIT = "WAIT"
    END_TURN = "END_TURN"


class AffordanceCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


class AffordanceProvenance(StrEnum):
    HANDCRAFTED_FIXTURE = "HANDCRAFTED_FIXTURE"
    GAME_PLAYER_AFFORDANCE = "GAME_PLAYER_AFFORDANCE"


class ResolutionStage(StrEnum):
    PREVIEW_RESOLVED = "PREVIEW_RESOLVED"
    SOURCE_RESOLVED = "SOURCE_RESOLVED"
    STATIC_RULE = "STATIC_RULE"


@dataclass(frozen=True, slots=True)
class ObservationPoint:
    round: int
    decision: int

    def __post_init__(self) -> None:
        if self.round < 0 or self.decision < 0:
            raise ValueError("observation coordinates must be non-negative")


@dataclass(frozen=True, slots=True)
class KnownValue:
    """An exact, uncertain, remembered, or deliberately unknown value."""

    representation: Representation
    knowledge_class: KnowledgeClass
    value: JsonValue = None
    minimum: int | float | None = None
    maximum: int | float | None = None
    candidates: tuple[JsonValue, ...] = ()
    distribution: tuple[tuple[JsonValue, float], ...] = ()
    observed_at: ObservationPoint | None = None
    basis: tuple[str, ...] = ()
    confidence: float | None = None

    def __post_init__(self) -> None:
        supplied = {
            Representation.EXACT: self.value is not None,
            Representation.RANGE: self.minimum is not None and self.maximum is not None,
            Representation.SET: bool(self.candidates),
            Representation.DISTRIBUTION: bool(self.distribution),
            Representation.UNKNOWN: self.value is None,
        }[self.representation]
        if not supplied:
            raise ValueError(f"missing payload for {self.representation}")
        if self.representation is Representation.UNKNOWN:
            if self.knowledge_class is not KnowledgeClass.UNKNOWN:
                raise ValueError("UNKNOWN representation requires UNKNOWN knowledge")
            if any(
                (
                    self.minimum is not None,
                    self.maximum is not None,
                    self.candidates,
                    self.distribution,
                )
            ):
                raise ValueError("UNKNOWN cannot carry a hidden value")
        elif self.knowledge_class is KnowledgeClass.UNKNOWN:
            raise ValueError("known representations cannot use UNKNOWN knowledge")
        if self.representation is Representation.RANGE and self.minimum > self.maximum:  # type: ignore[operator]
            raise ValueError("range minimum exceeds maximum")
        if (
            self.knowledge_class is KnowledgeClass.REMEMBERED
            and self.observed_at is None
        ):
            raise ValueError("REMEMBERED values require observed_at")
        if (
            self.knowledge_class in (KnowledgeClass.DERIVED, KnowledgeClass.INFERRED)
            and not self.basis
        ):
            raise ValueError("derived/inferred values require basis")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be in [0, 1]")
        if self.distribution:
            total = sum(probability for _, probability in self.distribution)
            if any(probability < 0 for _, probability in self.distribution):
                raise ValueError("distribution probabilities cannot be negative")
            if abs(total - 1.0) > 1e-9:
                raise ValueError("distribution probabilities must sum to 1")

    @classmethod
    def exact(
        cls, value: JsonValue, knowledge: KnowledgeClass = KnowledgeClass.EXACT_OBSERVED
    ) -> Self:
        return cls(Representation.EXACT, knowledge, value=value)

    @classmethod
    def unknown(cls) -> Self:
        return cls(Representation.UNKNOWN, KnowledgeClass.UNKNOWN)


@dataclass(frozen=True, order=True, slots=True)
class HexCoord:
    q: int
    r: int

    _DIRECTIONS = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))

    def neighbor(self, direction: int) -> HexCoord:
        if not 0 <= direction < 6:
            raise ValueError("hex direction must be in [0, 5]")
        dq, dr = self._DIRECTIONS[direction]
        return HexCoord(self.q + dq, self.r + dr)

    def distance_to(self, other: HexCoord) -> int:
        dq, dr = self.q - other.q, self.r - other.r
        return (abs(dq) + abs(dr) + abs(dq + dr)) // 2


@dataclass(frozen=True, slots=True)
class Tile:
    tile_id: str
    coordinate: HexCoord
    elevation: int
    terrain_id: str
    neighbors: tuple[str | None, ...]
    occupant_actor_id: str | None = None
    blocking: bool = False
    visibility: KnowledgeClass = KnowledgeClass.EXACT_OBSERVED
    dynamic_effect_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.tile_id or not self.terrain_id:
            raise ValueError("tile and terrain IDs cannot be empty")
        if len(self.neighbors) != 6:
            raise ValueError("tiles require six canonical neighbor slots")


@dataclass(frozen=True, slots=True)
class ItemState:
    item_id: str
    content_id: str
    slot: str
    condition: KnownValue = field(default_factory=KnownValue.unknown)
    ammunition: KnownValue = field(default_factory=KnownValue.unknown)


@dataclass(frozen=True, slots=True)
class EffectState:
    effect_id: str
    content_id: str
    stacks: KnownValue = field(default_factory=KnownValue.unknown)
    remaining_duration: KnownValue = field(default_factory=KnownValue.unknown)


@dataclass(frozen=True, slots=True)
class ResourceState:
    hit_points: KnownValue
    maximum_hit_points: KnownValue
    action_points: KnownValue
    maximum_action_points: KnownValue
    fatigue: KnownValue
    fatigue_capacity: KnownValue
    head_armor: KnownValue = field(default_factory=KnownValue.unknown)
    body_armor: KnownValue = field(default_factory=KnownValue.unknown)
    morale: KnownValue = field(default_factory=KnownValue.unknown)


@dataclass(frozen=True, slots=True)
class LastSeen:
    tile_id: str
    observed_at: ObservationPoint


@dataclass(frozen=True, slots=True)
class Combatant:
    actor_id: str
    relation: Relation
    is_player_controlled: bool
    life_state: LifeState
    visible: bool
    position: KnownValue
    resources: ResourceState
    faction_id: str | None = None
    content_id: str | None = None
    equipment: tuple[ItemState, ...] = ()
    effects: tuple[EffectState, ...] = ()
    skill_ids: tuple[str, ...] = ()
    perk_ids: tuple[str, ...] = ()
    last_seen: LastSeen | None = None


@dataclass(frozen=True, slots=True)
class RulesetIdentity:
    game_version: str
    content_fingerprint: str
    mods: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BattleContext:
    battle_id: str
    player_faction_id: str
    phase: str
    hostile_faction_ids: tuple[str, ...] = ()
    allied_faction_ids: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DecisionContext:
    active_actor_id: str
    round: int
    decision_index: int
    actor_has_waited: bool
    actor_may_wait: bool
    turn_phase: str
    prior_action_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TurnEntry:
    actor_id: str
    done: KnownValue
    sequence: KnownValue = field(default_factory=KnownValue.unknown)


@dataclass(frozen=True, slots=True)
class TurnState:
    entries: tuple[TurnEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class Environment:
    light: str
    weather: str | None = None
    effect_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResolvedCost:
    value: int
    stage: ResolutionStage
    authority: str

    def __post_init__(self) -> None:
        if self.value < 0 or not self.authority:
            raise ValueError("resolved costs require non-negative value and authority")


@dataclass(frozen=True, slots=True)
class PlayerVisiblePreview:
    displayed_hit_chance: int | None = None
    affected_tile_ids: tuple[str, ...] = ()
    displayed_damage: tuple[int, int] | None = None
    facts: tuple[tuple[str, JsonValue], ...] = ()

    def __post_init__(self) -> None:
        if (
            self.displayed_hit_chance is not None
            and not 0 <= self.displayed_hit_chance <= 100
        ):
            raise ValueError("displayed hit chance must be in [0, 100]")
        if self.displayed_damage is not None and (
            self.displayed_damage[0] < 0
            or self.displayed_damage[0] > self.displayed_damage[1]
        ):
            raise ValueError("invalid displayed damage range")


@dataclass(frozen=True, slots=True)
class ActionAffordance:
    action_id: str
    actor_id: str
    kind: ActionKind
    provenance: AffordanceProvenance
    source_generation: str
    parameters: tuple[tuple[str, JsonValue], ...] = ()
    ap_cost: ResolvedCost | None = None
    fatigue_cost: ResolvedCost | None = None
    skill_id: str | None = None
    item_id: str | None = None
    destination_tile_id: str | None = None
    resolved_path: tuple[str, ...] = ()
    preview: PlayerVisiblePreview = field(default_factory=PlayerVisiblePreview)
    debug_ground_truth: JsonValue = None

    def __post_init__(self) -> None:
        if not self.action_id or not self.actor_id or not self.source_generation:
            raise ValueError("affordance identity fields cannot be empty")
        if self.kind is ActionKind.MOVE_TO:
            if not self.destination_tile_id or not self.resolved_path:
                raise ValueError("MOVE_TO requires destination and resolved path")
            if self.resolved_path[-1] != self.destination_tile_id:
                raise ValueError("MOVE_TO path must end at destination")
            if self.ap_cost is None or self.fatigue_cost is None:
                raise ValueError("MOVE_TO requires resolved AP and fatigue costs")
        if self.kind is ActionKind.USE_SKILL and not self.skill_id:
            raise ValueError("USE_SKILL requires skill_id")
        if self.kind is ActionKind.EQUIP_ITEM and not self.item_id:
            raise ValueError("EQUIP_ITEM requires item_id")


@dataclass(frozen=True, slots=True)
class ActionAffordanceSet:
    actor_id: str
    captured_for_state_id: str
    source_generation: str
    completeness: AffordanceCompleteness
    actions: tuple[ActionAffordance, ...]


@dataclass(frozen=True, slots=True)
class TacticalState:
    contract_version: str
    state_id: str
    raw_capture_id: str | None
    information_profile: InformationProfile
    ruleset: RulesetIdentity
    battle: BattleContext
    decision: DecisionContext
    turn_state: TurnState
    environment: Environment
    tiles: tuple[Tile, ...]
    combatants: tuple[Combatant, ...]
    action_affordances: ActionAffordanceSet
    ground_entities: tuple[tuple[str, JsonValue], ...] = ()
    annotations: JsonValue = None

    def normalized(self) -> TacticalState:
        """Return a validated, deterministically ordered state with its semantic ID."""
        state = replace(
            self,
            state_id="",
            battle=replace(
                self.battle,
                hostile_faction_ids=tuple(sorted(set(self.battle.hostile_faction_ids))),
                allied_faction_ids=tuple(sorted(set(self.battle.allied_faction_ids))),
                flags=tuple(sorted(set(self.battle.flags))),
            ),
            environment=replace(
                self.environment,
                effect_ids=tuple(sorted(set(self.environment.effect_ids))),
            ),
            tiles=tuple(
                replace(
                    tile,
                    dynamic_effect_ids=tuple(sorted(set(tile.dynamic_effect_ids))),
                )
                for tile in sorted(self.tiles, key=lambda tile: tile.tile_id)
            ),
            combatants=tuple(
                replace(
                    actor,
                    equipment=tuple(
                        sorted(actor.equipment, key=lambda item: item.item_id)
                    ),
                    effects=tuple(
                        sorted(actor.effects, key=lambda effect: effect.effect_id)
                    ),
                    skill_ids=tuple(sorted(set(actor.skill_ids))),
                    perk_ids=tuple(sorted(set(actor.perk_ids))),
                )
                for actor in sorted(self.combatants, key=lambda actor: actor.actor_id)
            ),
            action_affordances=replace(
                self.action_affordances,
                actions=_normalize_actions(self.action_affordances.actions),
            ),
            ground_entities=tuple(sorted(self.ground_entities)),
        )
        state._validate_structure()
        state_id = canonical_sha256(state._identity_dict())
        if self.state_id and self.state_id != state_id:
            raise ValueError("state_id does not match normalized decision input")
        if self.action_affordances.captured_for_state_id != state_id:
            raise ValueError("stale affordance set: captured_for_state_id mismatch")
        return replace(state, state_id=state_id)

    @classmethod
    def create(cls, **values: Any) -> TacticalState:
        """Construct a state and populate its self-referential state/affordance IDs."""
        affordances = values["action_affordances"]
        provisional = cls(**values)
        unlinked = replace(
            provisional,
            state_id="",
            action_affordances=replace(affordances, captured_for_state_id=""),
        )
        normalized = replace(
            unlinked,
            battle=replace(
                unlinked.battle,
                hostile_faction_ids=tuple(
                    sorted(set(unlinked.battle.hostile_faction_ids))
                ),
                allied_faction_ids=tuple(
                    sorted(set(unlinked.battle.allied_faction_ids))
                ),
                flags=tuple(sorted(set(unlinked.battle.flags))),
            ),
            environment=replace(
                unlinked.environment,
                effect_ids=tuple(sorted(set(unlinked.environment.effect_ids))),
            ),
            tiles=tuple(
                replace(
                    tile,
                    dynamic_effect_ids=tuple(sorted(set(tile.dynamic_effect_ids))),
                )
                for tile in sorted(unlinked.tiles, key=lambda tile: tile.tile_id)
            ),
            combatants=tuple(
                replace(
                    actor,
                    equipment=tuple(
                        sorted(actor.equipment, key=lambda item: item.item_id)
                    ),
                    effects=tuple(
                        sorted(actor.effects, key=lambda effect: effect.effect_id)
                    ),
                    skill_ids=tuple(sorted(set(actor.skill_ids))),
                    perk_ids=tuple(sorted(set(actor.perk_ids))),
                )
                for actor in sorted(
                    unlinked.combatants, key=lambda actor: actor.actor_id
                )
            ),
            action_affordances=replace(
                unlinked.action_affordances,
                actions=_normalize_actions(unlinked.action_affordances.actions),
            ),
            ground_entities=tuple(sorted(unlinked.ground_entities)),
        )
        state_id = canonical_sha256(normalized._identity_dict())
        return replace(
            provisional,
            state_id=state_id,
            action_affordances=replace(affordances, captured_for_state_id=state_id),
        ).normalized()

    def to_dict(self, *, include_annotations: bool = True) -> dict[str, JsonValue]:
        value = _jsonify(asdict(self))
        assert isinstance(value, dict)
        if not include_annotations:
            value.pop("annotations", None)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, JsonValue]) -> TacticalState:
        """Deserialize and validate a canonical JSON-compatible mapping."""
        state = _construct(cls, value)
        assert isinstance(state, cls)
        return state.normalized()

    def _identity_dict(self) -> dict[str, JsonValue]:
        value = self.to_dict(include_annotations=False)
        value.pop("state_id", None)
        value.pop("raw_capture_id", None)
        affordances = value["action_affordances"]
        assert isinstance(affordances, dict)
        affordances.pop("captured_for_state_id", None)
        for action in affordances["actions"]:  # type: ignore[union-attr]
            action.pop("debug_ground_truth", None)
        return value

    def _validate_structure(self) -> None:
        if self.contract_version != CURRENT_VERSIONS.tactical_state:
            raise ValueError("unsupported tactical-state contract_version")
        if self.decision.round < 0 or self.decision.decision_index < 0:
            raise ValueError("decision coordinates must be non-negative")
        actors = {actor.actor_id: actor for actor in self.combatants}
        if len(actors) != len(self.combatants):
            raise ValueError("duplicate actor_id")
        tiles = {tile.tile_id: tile for tile in self.tiles}
        if len(tiles) != len(self.tiles):
            raise ValueError("duplicate tile_id")
        active = actors.get(self.decision.active_actor_id)
        if active is None or active.life_state is not LifeState.ALIVE:
            raise ValueError("active actor must resolve to a living combatant")
        if not active.is_player_controlled:
            raise ValueError("active actor must be player-controlled")
        if active.position.representation is not Representation.EXACT:
            raise ValueError("active actor must have an exact current position")
        if self.action_affordances.completeness is not AffordanceCompleteness.COMPLETE:
            raise ValueError("M1 rankable state requires a complete affordance set")
        if self.action_affordances.actor_id != active.actor_id:
            raise ValueError("affordance set actor does not match active actor")
        for entry in self.turn_state.entries:
            if entry.actor_id not in actors:
                raise ValueError("turn entry references unknown actor")
        if self.information_profile is InformationProfile.PLAYER_LEGAL:
            for value in _walk_known_values(self.turn_state):
                if value.knowledge_class is KnowledgeClass.DEBUG_GROUND_TRUTH:
                    raise ValueError("player_legal cannot contain DEBUG_GROUND_TRUTH")
            for tile in self.tiles:
                if tile.visibility is KnowledgeClass.DEBUG_GROUND_TRUTH:
                    raise ValueError("player_legal cannot contain DEBUG_GROUND_TRUTH")
        action_ids: set[str] = set()
        for action in self.action_affordances.actions:
            if action.actor_id != active.actor_id:
                raise ValueError("affordance actor does not match active actor")
            if action.source_generation != self.action_affordances.source_generation:
                raise ValueError("affordance source generation mismatch")
            if action.action_id in action_ids:
                raise ValueError("duplicate action_id")
            action_ids.add(action.action_id)
            if (
                self.information_profile is InformationProfile.PLAYER_LEGAL
                and action.debug_ground_truth is not None
            ):
                raise ValueError(
                    "player_legal cannot contain affordance DEBUG_GROUND_TRUTH"
                )
            if action.skill_id is not None and action.skill_id not in active.skill_ids:
                raise ValueError("affordance skill_id is not possessed by active actor")
            if action.item_id is not None and action.item_id not in {
                item.item_id for item in active.equipment
            }:
                raise ValueError("affordance item_id is not owned by active actor")
            for tile_id in (*action.resolved_path, *action.preview.affected_tile_ids):
                if tile_id not in tiles:
                    raise ValueError(f"affordance references unknown tile {tile_id}")
        exact_positions: dict[str, str] = {}
        for actor in self.combatants:
            _validate_resources(actor.resources)
            if actor.last_seen is not None and actor.last_seen.tile_id not in tiles:
                raise ValueError("last_seen references unknown tile")
            if self.information_profile is InformationProfile.PLAYER_LEGAL:
                _reject_debug_knowledge(actor)
                if actor.relation is Relation.HOSTILE and not actor.visible:
                    if actor.position.representation is Representation.EXACT:
                        raise ValueError(
                            "hidden hostile cannot have an exact current position"
                        )
            if actor.position.representation is Representation.EXACT:
                tile_id = actor.position.value
                if not isinstance(tile_id, str) or tile_id not in tiles:
                    raise ValueError("exact actor position must reference a tile")
                if tile_id in exact_positions:
                    raise ValueError("two actors cannot occupy one tile")
                exact_positions[tile_id] = actor.actor_id
                if tiles[tile_id].occupant_actor_id != actor.actor_id:
                    raise ValueError("actor position and tile occupancy disagree")
        for tile in self.tiles:
            if tile.occupant_actor_id is not None:
                if tile.occupant_actor_id not in actors:
                    raise ValueError("tile occupancy references unknown actor")
                if exact_positions.get(tile.tile_id) != tile.occupant_actor_id:
                    raise ValueError("tile occupancy and actor position disagree")
            for direction, neighbor_id in enumerate(tile.neighbors):
                if neighbor_id is None:
                    continue
                neighbor = tiles.get(neighbor_id)
                if neighbor is None:
                    raise ValueError("neighbor references unknown tile")
                if neighbor.coordinate != tile.coordinate.neighbor(direction):
                    raise ValueError(
                        "neighbor coordinate violates axial direction convention"
                    )
                if neighbor.neighbors[(direction + 3) % 6] != tile.tile_id:
                    raise ValueError("neighbor links must be symmetric")


def _reject_debug_knowledge(actor: Combatant) -> None:
    for value in _walk_known_values(actor):
        if value.knowledge_class is KnowledgeClass.DEBUG_GROUND_TRUTH:
            raise ValueError("player_legal cannot contain DEBUG_GROUND_TRUTH")


def _validate_resources(resources: ResourceState) -> None:
    non_negative = (
        resources.hit_points,
        resources.maximum_hit_points,
        resources.action_points,
        resources.maximum_action_points,
        resources.fatigue,
        resources.fatigue_capacity,
        resources.head_armor,
        resources.body_armor,
    )
    for value in non_negative:
        candidates: tuple[Any, ...] = ()
        if value.representation is Representation.EXACT:
            candidates = (value.value,)
        elif value.representation is Representation.RANGE:
            candidates = (value.minimum, value.maximum)
        if any(not isinstance(item, int | float) or item < 0 for item in candidates):
            raise ValueError("combat resource values must be non-negative numbers")
    for current, maximum, name in (
        (resources.hit_points, resources.maximum_hit_points, "hit points"),
        (resources.action_points, resources.maximum_action_points, "action points"),
        (resources.fatigue, resources.fatigue_capacity, "fatigue"),
    ):
        if (
            current.representation is Representation.EXACT
            and maximum.representation is Representation.EXACT
            and current.value > maximum.value  # type: ignore[operator]
        ):
            raise ValueError(f"current {name} exceeds declared maximum/capacity")


def _normalize_actions(
    actions: tuple[ActionAffordance, ...],
) -> tuple[ActionAffordance, ...]:
    unique: dict[str, ActionAffordance] = {}
    for action in actions:
        normalized = replace(
            action,
            parameters=tuple(sorted(action.parameters)),
            preview=replace(
                action.preview,
                affected_tile_ids=tuple(sorted(set(action.preview.affected_tile_ids))),
                facts=tuple(sorted(action.preview.facts)),
            ),
        )
        existing = unique.get(action.action_id)
        if existing is not None and existing != normalized:
            raise ValueError("conflicting affordances share an action_id")
        unique[action.action_id] = normalized
    return tuple(unique[action_id] for action_id in sorted(unique))


def _walk_known_values(value: Any) -> tuple[KnownValue, ...]:
    if isinstance(value, KnownValue):
        return (value,)
    if hasattr(value, "__dataclass_fields__"):
        result: tuple[KnownValue, ...] = ()
        for name in value.__dataclass_fields__:
            result += _walk_known_values(getattr(value, name))
        return result
    if isinstance(value, tuple):
        return sum((_walk_known_values(child) for child in value), ())
    return ()


def _jsonify(value: Any) -> JsonValue:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _jsonify(child) for key, child in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonify(child) for child in value]
    if value is None or isinstance(value, bool | int | float | str):
        return value
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _construct(annotation: Any, value: Any) -> Any:
    """Construct the closed contract type graph from JSON-compatible data."""
    if annotation is Any or annotation == JsonValue:
        return value
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (UnionType, getattr(__import__("typing"), "Union")):
        if value is None and type(None) in args:
            return None
        failures: list[Exception] = []
        for option in args:
            if option is type(None):
                continue
            try:
                return _construct(option, value)
            except (TypeError, ValueError, KeyError) as exc:
                failures.append(exc)
        raise TypeError(f"value does not match {annotation}: {failures}")
    if origin is tuple:
        if not isinstance(value, list | tuple):
            raise TypeError("tuple field must deserialize from an array")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_construct(args[0], child) for child in value)
        if len(value) != len(args):
            raise TypeError("fixed tuple has wrong length")
        return tuple(_construct(option, child) for option, child in zip(args, value))
    if isinstance(annotation, type) and issubclass(annotation, StrEnum):
        return annotation(value)
    if isinstance(annotation, type) and is_dataclass(annotation):
        if not isinstance(value, dict):
            raise TypeError(f"{annotation.__name__} must deserialize from an object")
        hints = get_type_hints(annotation)
        known = {item.name for item in fields(annotation)}
        unknown = set(value) - known
        if unknown:
            raise ValueError(f"unknown {annotation.__name__} fields: {sorted(unknown)}")
        return annotation(
            **{
                item.name: _construct(hints[item.name], value[item.name])
                for item in fields(annotation)
                if item.name in value
            }
        )
    if annotation in (str, int, float, bool):
        if (
            not isinstance(value, annotation)
            or annotation is int
            and isinstance(value, bool)
        ):
            raise TypeError(f"expected {annotation.__name__}")
        return value
    return value
