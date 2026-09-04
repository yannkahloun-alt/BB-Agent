"""Deterministic outcomes for the catalog-declared ordinary attack family."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from itertools import product

from bb_agent.mechanics import CoverageStatus, MechanicsAuthority
from bb_agent.results import ErrorCode, Problem, Result
from bb_agent.tactical_state import (
    ActionAffordance,
    ActionKind,
    InformationProfile,
    Representation,
    TacticalState,
)

MODEL_VERSION = "ordinary-attack.v1"
_HEAD_SHARE = 0.25
_ARMOR_DIRECT_MITIGATION = 0.1


class HitResult(StrEnum):
    MISS = "MISS"
    HEAD = "HEAD"
    BODY = "BODY"


@dataclass(frozen=True, slots=True)
class OutcomeBranch:
    result: HitResult
    probability: float
    damage: int = 0
    armor_damage: float = 0
    hp_damage: int = 0
    target_hp: int | None = None
    target_head_armor: float | None = None
    target_body_armor: float | None = None
    actor_action_points: int | None = None
    actor_fatigue: int | None = None
    killed: bool = False


@dataclass(frozen=True, slots=True)
class EpistemicScenario:
    """An unweighted legal hidden-state scenario, never an invented prior."""

    target_hp: int
    target_head_armor: int
    target_body_armor: int
    branches: tuple[OutcomeBranch, ...]

    @property
    def probability_mass(self) -> float:
        return sum(branch.probability for branch in self.branches)


@dataclass(frozen=True, slots=True)
class AttackOutcome:
    action_id: str
    model_version: str
    hit_chance: int
    branches: tuple[OutcomeBranch, ...]
    epistemic_scenarios: tuple[EpistemicScenario, ...] = ()
    aleatory: bool = True
    epistemic: bool = False

    @property
    def probability_mass(self) -> float | None:
        return (
            sum(branch.probability for branch in self.branches)
            if self.branches
            else None
        )

    @property
    def kill_probability(self) -> float | None:
        if not self.branches:
            return None
        return sum(branch.probability for branch in self.branches if branch.killed)


def _exact(value, label: str) -> int:
    if (
        value is None
        or value.representation is not Representation.EXACT
        or isinstance(value.value, bool)
        or not isinstance(value.value, int)
    ):
        raise ValueError(f"{label} must be exact for this outcome model")
    return value.value


def _values(value, label: str) -> tuple[tuple[int, float | None], ...]:
    """Return a justified distribution or an unweighted robustness domain."""
    if value.representation is Representation.EXACT:
        return ((_exact(value, label), 1.0),)
    if value.representation is Representation.DISTRIBUTION:
        if not all(
            isinstance(item, int) and not isinstance(item, bool)
            for item, _ in value.distribution
        ):
            raise ValueError(f"{label} distribution must contain integers")
        return tuple((item, probability) for item, probability in value.distribution)
    if value.representation is Representation.SET:
        if not all(
            isinstance(item, int) and not isinstance(item, bool)
            for item in value.candidates
        ):
            raise ValueError(f"{label} set must contain integers")
        return tuple((item, None) for item in sorted(value.candidates))
    if value.representation is Representation.RANGE:
        if not isinstance(value.minimum, int) or not isinstance(value.maximum, int):
            raise ValueError(f"{label} range must have integer endpoints")
        return tuple((item, None) for item in range(value.minimum, value.maximum + 1))
    raise ValueError(f"{label} is unknown and cannot be evaluated")


def _branches(
    *,
    hit_chance: int,
    low: int,
    high: int,
    armor_multiplier: float,
    direct_multiplier: float,
    head_multiplier: float,
    hp: int,
    head: int,
    body: int,
    actor_ap: int,
    actor_fatigue: int,
) -> tuple[OutcomeBranch, ...]:
    hit = hit_chance / 100
    roll_count = high - low + 1
    branches = [
        OutcomeBranch(
            HitResult.MISS,
            1 - hit,
            target_hp=hp,
            target_head_armor=head,
            target_body_armor=body,
            actor_action_points=actor_ap,
            actor_fatigue=actor_fatigue,
        )
    ]
    for location, share, body_multiplier in (
        (HitResult.HEAD, _HEAD_SHARE, head_multiplier),
        (HitResult.BODY, 1 - _HEAD_SHARE, 1.0),
    ):
        for regular_damage in range(low, high + 1):
            for armor_roll in range(low, high + 1):
                starting_armor = head if location is HitResult.HEAD else body
                armor_damage = min(starting_armor, armor_roll * armor_multiplier)
                remaining_armor = starting_armor - armor_damage
                damage = max(
                    0.0,
                    regular_damage * direct_multiplier
                    - remaining_armor * _ARMOR_DIRECT_MITIGATION,
                )
                if remaining_armor <= 0 or direct_multiplier >= 1:
                    damage += max(
                        0.0,
                        regular_damage * max(0.0, 1 - direct_multiplier) - armor_damage,
                    )
                hp_damage = max(0, int(damage * body_multiplier + 0.5))
                remaining_hp = max(0, hp - hp_damage)
                branches.append(
                    OutcomeBranch(
                        location,
                        hit * share / roll_count**2,
                        regular_damage,
                        armor_damage,
                        hp_damage,
                        remaining_hp,
                        max(0, head - armor_damage)
                        if location is HitResult.HEAD
                        else head,
                        max(0, body - armor_damage)
                        if location is HitResult.BODY
                        else body,
                        actor_ap,
                        actor_fatigue,
                        remaining_hp == 0,
                    )
                )
    return tuple(branches)


def evaluate_ordinary_attack(
    authority: MechanicsAuthority, state: TacticalState, action: ActionAffordance
) -> Result[AttackOutcome]:
    """Evaluate a vanilla hand-axe Chop without ranking or cloning legality."""
    try:
        if action.kind is not ActionKind.USE_SKILL or action.skill_id != "actives.chop":
            raise ValueError("action is not a supported ordinary attack")
        coverage = authority.classify(state)
        covered = next(
            item
            for item in (coverage.value.affordances if coverage.value else ())
            if item.action_id == action.action_id
        )
        if covered.status is not CoverageStatus.SUPPORTED:
            raise ValueError("ordinary attack is not covered by the active manifest")
        actor = next(
            item for item in state.combatants if item.actor_id == action.actor_id
        )
        target = next(
            item for item in state.combatants if item.actor_id == action.target_actor_id
        )
        if actor.effects or target.effects or target.equipment:
            raise ValueError(
                "ordinary attack has unmodelled effects or target equipment"
            )
        for combatant in (actor, target):
            if (
                combatant.perks.representation is not Representation.EXACT
                or combatant.perks.value not in ((), [])
                or combatant.traits.representation is not Representation.EXACT
                or combatant.traits.value not in ((), [])
            ):
                raise ValueError("ordinary attack has unmodelled perks or traits")
        preview = action.preview.displayed_hit_chance
        if (
            preview is None
            or isinstance(preview.value, bool)
            or not isinstance(preview.value, int)
        ):
            raise ValueError("ordinary attack requires an integer displayed hit chance")
        hit_chance = preview.value
        if not 5 <= hit_chance <= 95:
            raise ValueError(
                "ordinary attack requires a capped player-visible hit chance"
            )
        weapon = next(
            (
                item
                for item in actor.equipment
                if item.slot.value == "mainhand"
                and item.content.representation is Representation.EXACT
            ),
            None,
        )
        if weapon is None or not isinstance(weapon.content.value, str):
            raise ValueError("ordinary attack requires an exact mainhand weapon")
        if len(actor.equipment) != 1:
            raise ValueError("ordinary attack has unmodelled actor equipment")
        weapon_entry = authority.catalog.entry(weapon.content.value)
        skill_entry = authority.catalog.entry(action.skill_id)
        if weapon_entry is None or skill_entry is None:
            raise ValueError("weapon damage profile is unsupported")
        weapon_facts, skill_facts = dict(weapon_entry.facts), dict(skill_entry.facts)
        if "damage_min" not in weapon_facts:
            raise ValueError("weapon damage profile is unsupported")
        actor_ap = (
            _exact(actor.resources.action_points, "actor action points")
            - action.ap_cost.value
        )
        actor_fatigue = (
            _exact(actor.resources.fatigue, "actor fatigue") + action.fatigue_cost.value
        )
        if actor_ap < 0 or actor_fatigue > _exact(
            actor.resources.fatigue_capacity, "actor fatigue capacity"
        ):
            raise ValueError("resolved action costs exceed actor resources")
        kwargs = dict(
            hit_chance=hit_chance,
            low=int(weapon_facts["damage_min"]),
            high=int(weapon_facts["damage_max"]),
            armor_multiplier=float(weapon_facts["armor_damage_multiplier"]),
            direct_multiplier=float(skill_facts["direct_damage_multiplier"]),
            head_multiplier=1 + float(skill_facts["additional_head_damage_multiplier"]),
            actor_ap=actor_ap,
            actor_fatigue=actor_fatigue,
        )
        integrated: list[OutcomeBranch] = []
        scenarios: list[EpistemicScenario] = []
        for (hp, hp_probability), (head, head_probability), (
            body,
            body_probability,
        ) in product(
            _values(target.resources.hit_points, "target HP"),
            _values(target.resources.head_armor, "head armor"),
            _values(target.resources.body_armor, "body armor"),
        ):
            branches = _branches(**kwargs, hp=hp, head=head, body=body)
            if None in (hp_probability, head_probability, body_probability):
                scenarios.append(EpistemicScenario(hp, head, body, branches))
            else:
                weight = hp_probability * head_probability * body_probability
                integrated.extend(
                    replace(branch, probability=branch.probability * weight)
                    for branch in branches
                )
        if scenarios and integrated:
            raise ValueError(
                "mixed weighted and envelope target knowledge is unsupported"
            )
        return Result.success(
            AttackOutcome(
                action.action_id,
                MODEL_VERSION,
                hit_chance,
                tuple(integrated),
                tuple(scenarios),
                epistemic=bool(scenarios)
                or state.information_profile is InformationProfile.PLAYER_LEGAL
                and any(
                    value.representation is not Representation.EXACT
                    for value in (
                        target.resources.hit_points,
                        target.resources.head_armor,
                        target.resources.body_armor,
                    )
                ),
            )
        )
    except (AttributeError, StopIteration, TypeError, ValueError, KeyError) as exc:
        return Result.incomplete_coverage(
            Problem(
                ErrorCode.EVALUATION_UNSUPPORTED,
                str(exc),
                f"action_affordances.{action.action_id}",
                "ordinary_attack",
            )
        )
