"""Versioned canonical tactical-state and current-action affordance contracts."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass, replace
from enum import StrEnum
from types import MappingProxyType, UnionType
from typing import Any, Self, get_args, get_origin, get_type_hints

from bb_agent.serialization import JsonValue, canonical_json_bytes, canonical_sha256
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


class TargetKind(StrEnum):
    SELF = "SELF"
    ACTOR = "ACTOR"
    TILE = "TILE"
    DIRECTION = "DIRECTION"
    AREA = "AREA"


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


class ResolutionAuthority(StrEnum):
    PLAYER_UI = "PLAYER_UI"
    GAME_PLAYER_AFFORDANCE = "GAME_PLAYER_AFFORDANCE"
    HANDCRAFTED_FIXTURE = "HANDCRAFTED_FIXTURE"
    DEBUG_ORACLE = "DEBUG_ORACLE"


@dataclass(frozen=True, slots=True)
class ObservationPoint:
    round: int
    decision: int

    def __post_init__(self) -> None:
        _require_int(self.round, "observation round")
        _require_int(self.decision, "observation decision")
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
        object.__setattr__(self, "value", _freeze_json(self.value))
        object.__setattr__(
            self, "candidates", tuple(_freeze_json(value) for value in self.candidates)
        )
        object.__setattr__(
            self,
            "distribution",
            tuple(
                (_freeze_json(outcome), probability)
                for outcome, probability in self.distribution
            ),
        )
        object.__setattr__(self, "basis", tuple(self.basis))
        _require_enum(self.representation, Representation, "representation")
        _require_enum(self.knowledge_class, KnowledgeClass, "knowledge_class")
        payloads = {
            Representation.EXACT: self.value is not None,
            Representation.RANGE: self.minimum is not None or self.maximum is not None,
            Representation.SET: bool(self.candidates),
            Representation.DISTRIBUTION: bool(self.distribution),
        }
        expected = payloads.get(self.representation, False)
        if self.representation is Representation.RANGE:
            expected = self.minimum is not None and self.maximum is not None
        if self.representation is not Representation.UNKNOWN and not expected:
            raise ValueError(f"missing payload for {self.representation}")
        if any(
            present
            for representation, present in payloads.items()
            if representation is not self.representation
        ):
            raise ValueError("knowledge representation contains incompatible payload")
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
        if self.representation is Representation.RANGE:
            endpoints = (self.minimum, self.maximum)
            if any(
                isinstance(endpoint, bool)
                or not isinstance(endpoint, int | float)
                or not math.isfinite(endpoint)
                for endpoint in endpoints
            ):
                raise ValueError("range endpoints must be finite non-bool numbers")
            if self.minimum > self.maximum:  # type: ignore[operator]
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
        if self.confidence is not None:
            if (
                not isinstance(self.confidence, float)
                or not math.isfinite(self.confidence)
                or not 0 <= self.confidence <= 1
            ):
                raise ValueError("confidence must be a finite float in [0, 1]")
        if self.distribution:
            outcome_ids = tuple(
                _canonical_payload_bytes(outcome) for outcome, _ in self.distribution
            )
            if len(outcome_ids) != len(set(outcome_ids)):
                raise ValueError("distribution contains duplicate semantic outcomes")
            probabilities = tuple(probability for _, probability in self.distribution)
            if any(
                not isinstance(probability, float)
                or not math.isfinite(probability)
                or probability < 0
                for probability in probabilities
            ):
                raise ValueError(
                    "distribution probabilities must be finite nonnegative floats"
                )
            total = sum(probabilities)
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

    def __post_init__(self) -> None:
        _require_int(self.q, "hex q")
        _require_int(self.r, "hex r")

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
    terrain: KnownValue
    neighbors: tuple[str | None, ...]
    occupant_actor_id: str | None = None
    blocking: KnownValue = field(default_factory=KnownValue.unknown)
    visibility: KnowledgeClass = KnowledgeClass.EXACT_OBSERVED
    dynamic_effects: KnownValue = field(default_factory=KnownValue.unknown)
    movement_cost: KnownValue = field(default_factory=KnownValue.unknown)
    traversable: KnownValue = field(default_factory=KnownValue.unknown)
    blocks_line_of_sight: KnownValue = field(default_factory=KnownValue.unknown)

    def __post_init__(self) -> None:
        _require_int(self.elevation, "tile elevation")
        _require_enum(self.visibility, KnowledgeClass, "tile visibility")
        if not self.tile_id:
            raise ValueError("tile ID cannot be empty")
        if len(self.neighbors) != 6:
            raise ValueError("tiles require six canonical neighbor slots")


@dataclass(frozen=True, slots=True)
class ItemState:
    item_id: str
    content: KnownValue
    slot: KnownValue
    membership: KnownValue
    condition: KnownValue = field(default_factory=KnownValue.unknown)
    ammunition: KnownValue = field(default_factory=KnownValue.unknown)

    def __post_init__(self) -> None:
        if not self.item_id:
            raise ValueError("item_id cannot be empty")


@dataclass(frozen=True, slots=True)
class EffectState:
    effect_id: str
    content: KnownValue
    membership: KnownValue
    stacks: KnownValue = field(default_factory=KnownValue.unknown)
    remaining_duration: KnownValue = field(default_factory=KnownValue.unknown)

    def __post_init__(self) -> None:
        if not self.effect_id:
            raise ValueError("effect_id cannot be empty")


@dataclass(frozen=True, slots=True)
class GroundEntity:
    entity_id: str
    content: KnownValue
    position: KnownValue = field(default_factory=KnownValue.unknown)
    state: tuple[tuple[str, KnownValue], ...] = ()

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("ground entity ID cannot be empty")
        keys = tuple(key for key, _ in self.state)
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate ground entity state key")


@dataclass(frozen=True, slots=True)
class SkillState:
    skill_id: str
    possession: KnownValue
    enabled: KnownValue = field(default_factory=KnownValue.unknown)
    cooldown: KnownValue = field(default_factory=KnownValue.unknown)
    charges: KnownValue = field(default_factory=KnownValue.unknown)
    used_this_turn: KnownValue = field(default_factory=KnownValue.unknown)

    def __post_init__(self) -> None:
        if not self.skill_id:
            raise ValueError("skill_id cannot be empty")


@dataclass(frozen=True, slots=True)
class TacticalStat:
    stat_id: str
    value: KnownValue

    def __post_init__(self) -> None:
        if not self.stat_id:
            raise ValueError("stat_id cannot be empty")


@dataclass(frozen=True, slots=True)
class ResourceState:
    hit_points: KnownValue
    maximum_hit_points: KnownValue
    action_points: KnownValue
    maximum_action_points: KnownValue
    fatigue: KnownValue
    fatigue_capacity: KnownValue
    head_armor: KnownValue = field(default_factory=KnownValue.unknown)
    maximum_head_armor: KnownValue = field(default_factory=KnownValue.unknown)
    body_armor: KnownValue = field(default_factory=KnownValue.unknown)
    maximum_body_armor: KnownValue = field(default_factory=KnownValue.unknown)
    morale: KnownValue = field(default_factory=KnownValue.unknown)
    initiative: KnownValue = field(default_factory=KnownValue.unknown)

    def __post_init__(self) -> None:
        _validate_resources(self)


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
    faction: KnownValue = field(default_factory=KnownValue.unknown)
    content_identity: KnownValue = field(default_factory=KnownValue.unknown)
    equipment: tuple[ItemState, ...] = ()
    effects: tuple[EffectState, ...] = ()
    skills: tuple[SkillState, ...] = ()
    tactical_stats: tuple[TacticalStat, ...] = ()
    perks: KnownValue = field(default_factory=KnownValue.unknown)
    traits: KnownValue = field(default_factory=KnownValue.unknown)
    last_seen: LastSeen | None = None

    def __post_init__(self) -> None:
        if not self.actor_id:
            raise ValueError("actor_id cannot be empty")
        _require_bool(self.is_player_controlled, "is_player_controlled")
        _require_bool(self.visible, "visible")
        _require_enum(self.relation, Relation, "combatant relation")
        _require_enum(self.life_state, LifeState, "combatant life_state")


@dataclass(frozen=True, slots=True)
class RulesetIdentity:
    game_version: str
    content_fingerprint: str
    mods: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.game_version or not self.content_fingerprint:
            raise ValueError("ruleset identity fields cannot be empty")


@dataclass(frozen=True, slots=True)
class BattleContext:
    battle_id: str
    player_faction_id: str
    phase: str
    hostile_faction_ids: tuple[str, ...] = ()
    allied_faction_ids: tuple[str, ...] = ()
    flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.battle_id or not self.player_faction_id or not self.phase:
            raise ValueError("battle identity/context fields cannot be empty")


@dataclass(frozen=True, slots=True)
class DecisionContext:
    active_actor_id: str
    round: int
    decision_index: int
    actor_has_waited: bool
    actor_may_wait: bool
    turn_phase: str
    prior_action_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.active_actor_id or not self.turn_phase:
            raise ValueError("decision identity/context fields cannot be empty")
        _require_bool(self.actor_has_waited, "actor_has_waited")
        _require_bool(self.actor_may_wait, "actor_may_wait")
        _require_int(self.round, "decision round")
        _require_int(self.decision_index, "decision index")


@dataclass(frozen=True, slots=True)
class TurnEntry:
    actor_id: str
    done: KnownValue
    sequence: KnownValue = field(default_factory=KnownValue.unknown)

    def __post_init__(self) -> None:
        if not self.actor_id:
            raise ValueError("turn entry actor_id cannot be empty")


@dataclass(frozen=True, slots=True)
class TurnState:
    entries: tuple[TurnEntry, ...] = ()


@dataclass(frozen=True, slots=True)
class Environment:
    light: str
    weather: str | None = None
    effect_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.light:
            raise ValueError("environment light cannot be empty")


@dataclass(frozen=True, slots=True)
class ResolvedCost:
    value: int
    stage: ResolutionStage
    authority: ResolutionAuthority

    def __post_init__(self) -> None:
        _require_enum(self.stage, ResolutionStage, "resolved cost stage")
        _require_int(self.value, "resolved cost value")
        if self.value < 0:
            raise ValueError("resolved costs require a non-negative value")
        if not isinstance(self.authority, ResolutionAuthority):
            raise ValueError("resolved costs require a valid authority")


@dataclass(frozen=True, slots=True)
class ResolvedPreviewValue:
    value: JsonValue
    stage: ResolutionStage
    authority: ResolutionAuthority

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _freeze_json(self.value))
        _require_enum(self.stage, ResolutionStage, "resolved preview stage")
        if not isinstance(self.authority, ResolutionAuthority):
            raise ValueError("resolved preview values require a valid authority")


@dataclass(frozen=True, slots=True)
class PlayerVisiblePreview:
    displayed_hit_chance: ResolvedPreviewValue | None = None
    affected_tile_ids: ResolvedPreviewValue | None = None
    displayed_damage: ResolvedPreviewValue | None = None
    facts: tuple[tuple[str, ResolvedPreviewValue], ...] = ()

    def __post_init__(self) -> None:
        fact_keys = tuple(key for key, _ in self.facts)
        if len(fact_keys) != len(set(fact_keys)):
            raise ValueError("duplicate player-visible preview fact key")
        if self.displayed_hit_chance is not None:
            chance = self.displayed_hit_chance.value
            if (
                isinstance(chance, bool)
                or not isinstance(chance, int)
                or not 0 <= chance <= 100
            ):
                raise ValueError("displayed hit chance must be an integer in [0, 100]")
        if self.displayed_damage is not None:
            damage = self.displayed_damage.value
            if (
                not isinstance(damage, list | tuple)
                or len(damage) != 2
                or any(
                    isinstance(item, bool) or not isinstance(item, int)
                    for item in damage
                )
                or damage[0] < 0
                or damage[0] > damage[1]
            ):
                raise ValueError("invalid displayed damage range")
        if self.affected_tile_ids is not None:
            affected = self.affected_tile_ids.value
            if not isinstance(affected, list | tuple) or not all(
                isinstance(tile_id, str) for tile_id in affected
            ):
                raise ValueError("affected tile preview must contain tile IDs")


@dataclass(frozen=True, slots=True)
class ActionAffordance:
    action_id: str
    actor_id: str
    kind: ActionKind
    provenance: AffordanceProvenance
    source_generation: str
    parameters: tuple[tuple[str, KnownValue], ...] = ()
    ap_cost: ResolvedCost | None = None
    fatigue_cost: ResolvedCost | None = None
    skill_id: str | None = None
    item_id: str | None = None
    target_kind: TargetKind | None = None
    target_actor_id: str | None = None
    target_tile_id: str | None = None
    target_direction: int | None = None
    mode_variant: str | None = None
    destination_tile_id: str | None = None
    resolved_path: tuple[str, ...] = ()
    source_location: str | None = None
    target_slot: str | None = None
    displaced_item_id: str | None = None
    displaced_item_destination: str | None = None
    preview: PlayerVisiblePreview = field(default_factory=PlayerVisiblePreview)
    debug_ground_truth: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "debug_ground_truth", _freeze_json(self.debug_ground_truth)
        )
        _require_enum(self.kind, ActionKind, "affordance kind")
        _require_enum(self.provenance, AffordanceProvenance, "affordance provenance")
        if self.target_kind is not None:
            _require_enum(self.target_kind, TargetKind, "affordance target_kind")
        if not self.action_id or not self.actor_id or not self.source_generation:
            raise ValueError("affordance identity fields cannot be empty")
        if not isinstance(self.provenance, AffordanceProvenance):
            raise ValueError("affordance requires an allowed provenance")
        parameter_keys = tuple(key for key, _ in self.parameters)
        if len(parameter_keys) != len(set(parameter_keys)):
            raise ValueError("duplicate affordance parameter key")
        if any(not key.startswith("extension.") for key in parameter_keys):
            raise ValueError("generic parameters require the extension namespace")
        if self.mode_variant == "":
            raise ValueError("mode_variant cannot be empty")
        if self.ap_cost is None or self.fatigue_cost is None:
            raise ValueError("every affordance requires resolved AP and fatigue costs")
        if self.kind is ActionKind.MOVE_TO:
            if not self.destination_tile_id or not self.resolved_path:
                raise ValueError("MOVE_TO requires destination and resolved path")
            if self.resolved_path[-1] != self.destination_tile_id:
                raise ValueError("MOVE_TO path must end at destination")
            if self.ap_cost is None or self.fatigue_cost is None:
                raise ValueError("MOVE_TO requires resolved AP and fatigue costs")
            if any(
                value is not None
                for value in (
                    self.skill_id,
                    self.item_id,
                    self.target_kind,
                    self.target_actor_id,
                    self.target_tile_id,
                    self.target_direction,
                    self.mode_variant,
                    self.source_location,
                    self.target_slot,
                    self.displaced_item_id,
                    self.displaced_item_destination,
                )
            ):
                raise ValueError("MOVE_TO contains incompatible action fields")
        elif self.kind is ActionKind.USE_SKILL:
            self._validate_skill_target()
            if (
                any(
                    value is not None
                    for value in (
                        self.item_id,
                        self.destination_tile_id,
                        self.source_location,
                        self.target_slot,
                        self.displaced_item_id,
                        self.displaced_item_destination,
                    )
                )
                or self.resolved_path
            ):
                raise ValueError("USE_SKILL contains incompatible action fields")
        elif self.kind is ActionKind.EQUIP_ITEM:
            if not self.item_id or not self.source_location or not self.target_slot:
                raise ValueError(
                    "EQUIP_ITEM requires item_id, source_location, and target_slot"
                )
            if self.displaced_item_id and not self.displaced_item_destination:
                raise ValueError("displaced item requires its destination")
            if (
                any(
                    value is not None
                    for value in (
                        self.skill_id,
                        self.target_kind,
                        self.target_actor_id,
                        self.target_tile_id,
                        self.target_direction,
                        self.mode_variant,
                        self.destination_tile_id,
                    )
                )
                or self.resolved_path
            ):
                raise ValueError("EQUIP_ITEM contains incompatible action fields")
        elif (
            any(
                value is not None
                for value in (
                    self.skill_id,
                    self.item_id,
                    self.target_kind,
                    self.target_actor_id,
                    self.target_tile_id,
                    self.target_direction,
                    self.mode_variant,
                    self.destination_tile_id,
                    self.source_location,
                    self.target_slot,
                    self.displaced_item_id,
                    self.displaced_item_destination,
                )
            )
            or self.resolved_path
        ):
            raise ValueError(f"{self.kind} contains incompatible action fields")

    def _validate_skill_target(self) -> None:
        if not self.skill_id or self.target_kind is None:
            raise ValueError("USE_SKILL requires skill_id and target_kind")
        if self.target_direction is not None:
            _require_int(self.target_direction, "target_direction")
            if not 0 <= self.target_direction <= 5:
                raise ValueError("target_direction must be in [0, 5]")
        actor = self.target_actor_id is not None
        tile = self.target_tile_id is not None
        direction = self.target_direction is not None
        expected = {
            TargetKind.SELF: (False, False, False),
            TargetKind.ACTOR: (True, False, False),
            TargetKind.TILE: (False, True, False),
            TargetKind.DIRECTION: (False, False, True),
            TargetKind.AREA: (False, True, direction),
        }[self.target_kind]
        if (actor, tile, direction) != expected:
            raise ValueError("USE_SKILL target fields do not match target_kind")


@dataclass(frozen=True, slots=True)
class ActionAffordanceSet:
    actor_id: str
    captured_for_state_id: str
    source_generation: str
    completeness: AffordanceCompleteness
    actions: tuple[ActionAffordance, ...]

    def __post_init__(self) -> None:
        _require_enum(self.completeness, AffordanceCompleteness, "completeness")
        if not self.actor_id:
            raise ValueError("affordance set actor_id cannot be empty")
        if not self.source_generation:
            raise ValueError("affordance set source_generation cannot be empty")
        if self.completeness is AffordanceCompleteness.COMPLETE and not self.actions:
            raise ValueError("complete affordance set must contain at least one action")


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
    ground_entities: tuple[GroundEntity, ...] = ()
    annotations: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "annotations", _freeze_json(self.annotations))
        _require_enum(
            self.information_profile, InformationProfile, "information_profile"
        )

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
            tiles=tuple(sorted(self.tiles, key=lambda tile: tile.tile_id)),
            combatants=tuple(
                replace(
                    actor,
                    equipment=tuple(
                        sorted(actor.equipment, key=lambda item: item.item_id)
                    ),
                    effects=tuple(
                        sorted(actor.effects, key=lambda effect: effect.effect_id)
                    ),
                    skills=tuple(
                        sorted(actor.skills, key=lambda skill: skill.skill_id)
                    ),
                    tactical_stats=tuple(
                        sorted(actor.tactical_stats, key=lambda stat: stat.stat_id)
                    ),
                )
                for actor in sorted(self.combatants, key=lambda actor: actor.actor_id)
            ),
            action_affordances=replace(
                self.action_affordances,
                actions=_normalize_actions(self.action_affordances.actions),
            ),
            ground_entities=tuple(
                replace(entity, state=tuple(sorted(entity.state)))
                for entity in sorted(
                    self.ground_entities, key=lambda entity: entity.entity_id
                )
            ),
        )
        state = _normalize_epistemic(state)
        assert isinstance(state, TacticalState)
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
            tiles=tuple(sorted(unlinked.tiles, key=lambda tile: tile.tile_id)),
            combatants=tuple(
                replace(
                    actor,
                    equipment=tuple(
                        sorted(actor.equipment, key=lambda item: item.item_id)
                    ),
                    effects=tuple(
                        sorted(actor.effects, key=lambda effect: effect.effect_id)
                    ),
                    skills=tuple(
                        sorted(actor.skills, key=lambda skill: skill.skill_id)
                    ),
                    tactical_stats=tuple(
                        sorted(actor.tactical_stats, key=lambda stat: stat.stat_id)
                    ),
                )
                for actor in sorted(
                    unlinked.combatants, key=lambda actor: actor.actor_id
                )
            ),
            action_affordances=replace(
                unlinked.action_affordances,
                actions=_normalize_actions(unlinked.action_affordances.actions),
            ),
            ground_entities=tuple(
                replace(entity, state=tuple(sorted(entity.state)))
                for entity in sorted(
                    unlinked.ground_entities, key=lambda entity: entity.entity_id
                )
            ),
        )
        normalized = _normalize_epistemic(normalized)
        assert isinstance(normalized, TacticalState)
        state_id = canonical_sha256(normalized._identity_dict())
        return replace(
            provisional,
            state_id=state_id,
            action_affordances=replace(affordances, captured_for_state_id=state_id),
        ).normalized()

    def to_dict(self, *, include_annotations: bool = True) -> dict[str, JsonValue]:
        value = _jsonify(self)
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
        affordances.pop("source_generation", None)
        for action in affordances["actions"]:  # type: ignore[union-attr]
            action.pop("debug_ground_truth", None)
            action.pop("source_generation", None)
            action.pop("provenance", None)
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
        ground_entities = {entity.entity_id: entity for entity in self.ground_entities}
        if len(ground_entities) != len(self.ground_entities):
            raise ValueError("duplicate ground entity ID")
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
        command_intents: dict[str, str] = {}
        for action in self.action_affordances.actions:
            if action.actor_id != active.actor_id:
                raise ValueError("affordance actor does not match active actor")
            if action.source_generation != self.action_affordances.source_generation:
                raise ValueError("affordance source generation mismatch")
            if action.action_id in action_ids:
                raise ValueError("duplicate action_id")
            action_ids.add(action.action_id)
            intent = canonical_sha256(_command_intent(action))
            if action.action_id != f"action:{intent}":
                raise ValueError("action_id does not match canonical command intent")
            prior_action_id = command_intents.get(intent)
            if prior_action_id is not None and prior_action_id != action.action_id:
                raise ValueError("duplicate executable command has different action_id")
            command_intents[intent] = action.action_id
            if (
                self.information_profile is InformationProfile.PLAYER_LEGAL
                and action.debug_ground_truth is not None
            ):
                raise ValueError(
                    "player_legal cannot contain affordance DEBUG_GROUND_TRUTH"
                )
            if self.information_profile is InformationProfile.PLAYER_LEGAL:
                if any(
                    value.knowledge_class is KnowledgeClass.DEBUG_GROUND_TRUTH
                    for _, value in action.parameters
                ):
                    raise ValueError(
                        "player_legal cannot contain extension DEBUG_GROUND_TRUTH"
                    )
                for preview_value in _preview_values(action.preview):
                    if preview_value.authority is ResolutionAuthority.DEBUG_ORACLE:
                        raise ValueError(
                            "player_legal cannot consume DEBUG_ORACLE preview"
                        )
                for cost in (action.ap_cost, action.fatigue_cost):
                    if (
                        cost is not None
                        and cost.authority is ResolutionAuthority.DEBUG_ORACLE
                    ):
                        raise ValueError(
                            "player_legal cannot consume DEBUG_ORACLE cost"
                        )
            _validate_action_authorities(action, self.information_profile)
            if action.skill_id is not None and action.skill_id not in {
                skill.skill_id for skill in active.skills
            }:
                raise ValueError("affordance skill_id is not possessed by active actor")
            if action.item_id is not None and action.item_id not in {
                item.item_id for item in active.equipment
            }:
                raise ValueError("affordance item_id is not owned by active actor")
            if (
                action.displaced_item_id is not None
                and action.displaced_item_id
                not in {item.item_id for item in active.equipment}
            ):
                raise ValueError("displaced_item_id is not owned by active actor")
            if (
                action.target_actor_id is not None
                and action.target_actor_id not in actors
            ):
                raise ValueError("affordance target_actor_id references unknown actor")
            if action.target_tile_id is not None and action.target_tile_id not in tiles:
                raise ValueError("affordance target_tile_id references unknown tile")
            affected_tiles: tuple[str, ...] = ()
            if action.preview.affected_tile_ids is not None:
                affected_tiles = tuple(action.preview.affected_tile_ids.value)  # type: ignore[arg-type]
            for tile_id in (*action.resolved_path, *affected_tiles):
                if tile_id not in tiles:
                    raise ValueError(f"affordance references unknown tile {tile_id}")
            if action.kind is ActionKind.MOVE_TO:
                origin = active.position.value
                assert isinstance(origin, str)
                prior = origin
                for step in action.resolved_path:
                    if step not in tiles[prior].neighbors:
                        raise ValueError(
                            "MOVE_TO resolved path contains a non-adjacent step"
                        )
                    prior = step
        exact_positions: dict[str, str] = {}
        for actor in self.combatants:
            _validate_resources(actor.resources)
            for values, label in (
                ((item.item_id for item in actor.equipment), "item_id"),
                ((effect.effect_id for effect in actor.effects), "effect_id"),
                ((skill.skill_id for skill in actor.skills), "skill_id"),
                ((stat.stat_id for stat in actor.tactical_stats), "stat_id"),
            ):
                identifiers = tuple(values)
                if len(identifiers) != len(set(identifiers)):
                    raise ValueError(f"duplicate combatant {label}")
            if actor.last_seen is not None and actor.last_seen.tile_id not in tiles:
                raise ValueError("last_seen references unknown tile")
            if self.information_profile is InformationProfile.PLAYER_LEGAL:
                _reject_debug_knowledge(actor)
                if actor.relation is Relation.HOSTILE:
                    _validate_hostile_player_legal(actor)
                if actor.relation is Relation.HOSTILE and not actor.visible:
                    if (
                        actor.position.representation is not Representation.UNKNOWN
                        and actor.position.knowledge_class
                        is not KnowledgeClass.INFERRED
                    ):
                        raise ValueError(
                            "hidden hostile current position must be UNKNOWN "
                            "or INFERRED"
                        )
                    _validate_hidden_hostile_staleness(actor)
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
            if self.information_profile is InformationProfile.PLAYER_LEGAL:
                for knowledge in _walk_knowledge_classes(tile):
                    if knowledge is KnowledgeClass.DEBUG_GROUND_TRUTH:
                        raise ValueError(
                            "player_legal cannot contain DEBUG_GROUND_TRUTH"
                        )
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
        for entity in self.ground_entities:
            _validate_ground_entity_position(entity, tiles)
            if self.information_profile is InformationProfile.PLAYER_LEGAL:
                for knowledge in _walk_knowledge_classes(entity):
                    if knowledge is KnowledgeClass.DEBUG_GROUND_TRUTH:
                        raise ValueError(
                            "player_legal cannot contain ground entity "
                            "DEBUG_GROUND_TRUTH"
                        )


def _reject_debug_knowledge(actor: Combatant) -> None:
    for knowledge in _walk_knowledge_classes(actor):
        if knowledge is KnowledgeClass.DEBUG_GROUND_TRUTH:
            raise ValueError("player_legal cannot contain DEBUG_GROUND_TRUTH")


def _walk_knowledge_classes(value: Any) -> tuple[KnowledgeClass, ...]:
    if isinstance(value, KnownValue):
        return (value.knowledge_class,)
    if hasattr(value, "__dataclass_fields__"):
        result: tuple[KnowledgeClass, ...] = ()
        for name in value.__dataclass_fields__:
            result += _walk_knowledge_classes(getattr(value, name))
        return result
    if isinstance(value, tuple):
        return sum((_walk_knowledge_classes(child) for child in value), ())
    return ()


def _validate_hidden_hostile_staleness(actor: Combatant) -> None:
    prohibited = {KnowledgeClass.EXACT_OBSERVED, KnowledgeClass.OBSERVED}
    changeable: list[KnowledgeClass] = [
        value.knowledge_class for value in _walk_known_values(actor.resources)
    ]
    changeable.extend(
        (
            actor.content_identity.knowledge_class,
            actor.faction.knowledge_class,
            actor.perks.knowledge_class,
            actor.traits.knowledge_class,
        )
    )
    changeable.extend(
        value.knowledge_class
        for skill in actor.skills
        for value in _walk_known_values(skill)
    )
    changeable.extend(stat.value.knowledge_class for stat in actor.tactical_stats)
    for item in actor.equipment:
        changeable.extend(value.knowledge_class for value in _walk_known_values(item))
    for effect in actor.effects:
        changeable.extend(value.knowledge_class for value in _walk_known_values(effect))
    if any(knowledge in prohibited for knowledge in changeable):
        raise ValueError("hidden hostile changeable state must be stale or uncertain")


def _validate_hostile_player_legal(actor: Combatant) -> None:
    prohibited = {KnowledgeClass.EXACT_OBSERVED, KnowledgeClass.OBSERVED}
    numeric_values = list(_walk_known_values(actor.resources))
    numeric_values.extend(stat.value for stat in actor.tactical_stats)
    if any(
        value.representation is Representation.EXACT
        and value.knowledge_class in prohibited
        and isinstance(value.value, int | float)
        and not isinstance(value.value, bool)
        for value in numeric_values
    ):
        raise ValueError("player_legal hostile numeric state cannot be exact observed")


def _preview_values(preview: PlayerVisiblePreview) -> tuple[ResolvedPreviewValue, ...]:
    values = tuple(
        value
        for value in (
            preview.displayed_hit_chance,
            preview.affected_tile_ids,
            preview.displayed_damage,
        )
        if value is not None
    )
    return values + tuple(value for _, value in preview.facts)


def _validate_action_authorities(
    action: ActionAffordance, profile: InformationProfile
) -> None:
    provider_authority = {
        AffordanceProvenance.HANDCRAFTED_FIXTURE: (
            ResolutionAuthority.HANDCRAFTED_FIXTURE
        ),
        AffordanceProvenance.GAME_PLAYER_AFFORDANCE: (
            ResolutionAuthority.GAME_PLAYER_AFFORDANCE
        ),
    }[action.provenance]
    allowed = {provider_authority, ResolutionAuthority.PLAYER_UI}
    if profile is InformationProfile.OMNISCIENT_DEBUG:
        allowed.add(ResolutionAuthority.DEBUG_ORACLE)
    authorities = [action.ap_cost.authority, action.fatigue_cost.authority]  # type: ignore[union-attr]
    authorities.extend(value.authority for value in _preview_values(action.preview))
    if any(authority not in allowed for authority in authorities):
        raise ValueError("resolved authority does not match affordance provenance")


def _validate_ground_entity_position(
    entity: GroundEntity, tiles: dict[str, Tile]
) -> None:
    position = entity.position
    if position.representation is Representation.UNKNOWN:
        return
    if position.representation is Representation.EXACT:
        tile_ids = (position.value,)
    elif position.representation is Representation.SET:
        tile_ids = position.candidates
    elif position.representation is Representation.DISTRIBUTION:
        tile_ids = tuple(outcome for outcome, _ in position.distribution)
    else:
        raise ValueError("ground entity position cannot use RANGE representation")
    if any(
        not isinstance(tile_id, str) or tile_id not in tiles for tile_id in tile_ids
    ):
        raise ValueError("ground entity position references unknown tile")


def _validate_resources(resources: ResourceState) -> None:
    non_negative = (
        resources.hit_points,
        resources.maximum_hit_points,
        resources.action_points,
        resources.maximum_action_points,
        resources.fatigue,
        resources.fatigue_capacity,
        resources.head_armor,
        resources.maximum_head_armor,
        resources.body_armor,
        resources.maximum_body_armor,
        resources.initiative,
    )
    for value in non_negative:
        candidates: tuple[Any, ...] = ()
        if value.representation is Representation.EXACT:
            candidates = (value.value,)
        elif value.representation is Representation.RANGE:
            candidates = (value.minimum, value.maximum)
        elif value.representation is Representation.SET:
            candidates = value.candidates
        elif value.representation is Representation.DISTRIBUTION:
            candidates = tuple(outcome for outcome, _ in value.distribution)
        if any(
            isinstance(item, bool) or not isinstance(item, int) or item < 0
            for item in candidates
        ):
            raise ValueError("combat resource values must be non-negative integers")
    for current, maximum, name in (
        (resources.hit_points, resources.maximum_hit_points, "hit points"),
        (resources.action_points, resources.maximum_action_points, "action points"),
        (resources.fatigue, resources.fatigue_capacity, "fatigue"),
        (resources.head_armor, resources.maximum_head_armor, "head armor"),
        (resources.body_armor, resources.maximum_body_armor, "body armor"),
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
        affected = action.preview.affected_tile_ids
        if affected is not None:
            affected = replace(
                affected,
                value=sorted(set(affected.value)),  # type: ignore[arg-type]
            )
        normalized = replace(
            action,
            parameters=tuple(sorted(action.parameters)),
            preview=replace(
                action.preview,
                affected_tile_ids=affected,
                facts=tuple(sorted(action.preview.facts)),
            ),
        )
        normalized = replace(
            normalized,
            action_id=f"action:{canonical_sha256(_command_intent(normalized))}",
        )
        existing = unique.get(normalized.action_id)
        if existing is not None and existing != normalized:
            raise ValueError("conflicting affordances share an action_id")
        unique[normalized.action_id] = normalized
    return tuple(unique[action_id] for action_id in sorted(unique))


def _command_intent(action: ActionAffordance) -> dict[str, JsonValue]:
    return {
        "actor_id": action.actor_id,
        "kind": action.kind.value,
        "parameters": _jsonify(action.parameters),
        "skill_id": action.skill_id,
        "item_id": action.item_id,
        "target_kind": action.target_kind.value if action.target_kind else None,
        "target_actor_id": action.target_actor_id,
        "target_tile_id": action.target_tile_id,
        "target_direction": action.target_direction,
        "mode_variant": action.mode_variant,
        "destination_tile_id": action.destination_tile_id,
        "resolved_path": _jsonify(action.resolved_path),
        "source_location": action.source_location,
        "target_slot": action.target_slot,
        "displaced_item_id": action.displaced_item_id,
        "displaced_item_destination": action.displaced_item_destination,
    }


def _normalize_epistemic(value: Any) -> Any:
    if isinstance(value, KnownValue):
        candidates = value.candidates
        if value.representation is Representation.SET:
            unique_candidates = {
                _canonical_payload_bytes(candidate): candidate
                for candidate in candidates
            }
            candidates = tuple(
                unique_candidates[key] for key in sorted(unique_candidates)
            )
        distribution = value.distribution
        if value.representation is Representation.DISTRIBUTION:
            distribution = tuple(
                sorted(
                    distribution, key=lambda entry: _canonical_payload_bytes(entry[0])
                )
            )
        return replace(
            value,
            candidates=candidates,
            distribution=distribution,
            basis=tuple(sorted(set(value.basis))),
        )
    if is_dataclass(value):
        return replace(
            value,
            **{
                item.name: _normalize_epistemic(getattr(value, item.name))
                for item in fields(value)
            },
        )
    if isinstance(value, tuple):
        return tuple(_normalize_epistemic(child) for child in value)
    return value


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


def _require_enum(value: Any, enum_type: type[StrEnum], field_name: str) -> None:
    if not isinstance(value, enum_type):
        raise ValueError(f"{field_name} requires {enum_type.__name__}")


def _require_int(value: Any, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} requires an integer")


def _require_bool(value: Any, field_name: str) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} requires a boolean")


def _freeze_json(value: Any) -> Any:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON payload cannot contain non-finite floats")
        return value
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("JSON object keys must be strings")
        return MappingProxyType(
            {key: _freeze_json(child) for key, child in sorted(value.items())}
        )
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return tuple(_freeze_json(child) for child in value)
    raise TypeError(f"unsupported JSON payload: {type(value).__name__}")


def _canonical_payload_bytes(value: Any) -> bytes:
    return canonical_json_bytes(_jsonify(value))


def _jsonify(value: Any) -> JsonValue:
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _jsonify(getattr(value, item.name)) for item in fields(value)
        }
    if isinstance(value, Mapping):
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
