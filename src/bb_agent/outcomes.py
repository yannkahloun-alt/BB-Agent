"""Deterministic ordinary single-target attack outcomes.

This module deliberately models only the small ordinary-attack family declared
by the M1 catalog.  Preview values are inputs owned by the source affordance;
they are never reconstructed from hidden combat statistics.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from itertools import product

from bb_agent.mechanics import MechanicsAuthority
from bb_agent.results import ErrorCode, Problem, Result
from bb_agent.tactical_state import (
    ActionAffordance,
    ActionKind,
    InformationProfile,
    Representation,
    TacticalState,
)

MODEL_VERSION = "ordinary-attack.v1"


class HitResult(StrEnum):
    MISS = "MISS"
    HEAD = "HEAD"
    BODY = "BODY"


@dataclass(frozen=True, slots=True)
class OutcomeBranch:
    result: HitResult
    probability: float
    damage: int = 0
    armor_damage: int = 0
    hp_damage: int = 0
    target_hp: int | None = None
    target_head_armor: int | None = None
    target_body_armor: int | None = None
    killed: bool = False


@dataclass(frozen=True, slots=True)
class AttackOutcome:
    action_id: str
    model_version: str
    hit_chance: int
    branches: tuple[OutcomeBranch, ...]
    aleatory: bool = True
    epistemic: bool = False

    @property
    def probability_mass(self) -> float:
        return sum(branch.probability for branch in self.branches)

    @property
    def kill_probability(self) -> float:
        return sum(b.probability for b in self.branches if b.killed)


def _exact(value, label: str) -> int:
    if value.representation is not Representation.EXACT or not isinstance(
        value.value, int
    ):
        raise ValueError(f"{label} must be exact for this outcome model")
    return value.value


def _possibilities(value, label: str) -> tuple[tuple[int, float], ...]:
    """Expand only declared finite knowledge; never invent an unknown midpoint."""
    if value.representation is Representation.EXACT:
        return ((_exact(value, label), 1.0),)
    if value.representation is Representation.SET:
        values = tuple(
            sorted({item for item in value.candidates if isinstance(item, int)})
        )
        if len(values) != len(value.candidates) or not values:
            raise ValueError(f"{label} set must contain integers")
        return tuple((item, 1.0 / len(values)) for item in values)
    if value.representation is Representation.DISTRIBUTION:
        if not all(isinstance(item, int) for item, _ in value.distribution):
            raise ValueError(f"{label} distribution must contain integers")
        return tuple((item, probability) for item, probability in value.distribution)
    if value.representation is Representation.RANGE:
        # A range is an envelope, not an implied uniform distribution.
        return ((int(value.minimum), 0.5), (int(value.maximum), 0.5))
    raise ValueError(f"{label} is unknown and cannot be evaluated")


def evaluate_ordinary_attack(
    authority: MechanicsAuthority, state: TacticalState, action: ActionAffordance
) -> Result[AttackOutcome]:
    """Evaluate one manifest-declared ordinary attack, without ranking it."""
    try:
        if action.kind is not ActionKind.USE_SKILL or action.skill_id != "actives.chop":
            raise ValueError("action is not a supported ordinary attack")
        coverage = authority.classify(state)
        covered = next(
            (
                a
                for a in (coverage.value.affordances if coverage.value else ())
                if a.action_id == action.action_id
            ),
            None,
        )
        if covered is None or covered.status.value != "SUPPORTED":
            raise ValueError("ordinary attack is not covered by the active manifest")
        actor = next(a for a in state.combatants if a.actor_id == action.actor_id)
        target = next(
            a for a in state.combatants if a.actor_id == action.target_actor_id
        )
        chance = action.preview.displayed_hit_chance
        if chance is None:
            raise ValueError("ordinary attack requires a player-visible hit chance")
        hit_chance = _exact(chance, "displayed hit chance")
        weapon = next(
            (
                i
                for i in actor.equipment
                if i.slot.value == "mainhand"
                and i.content.representation is Representation.EXACT
            ),
            None,
        )
        if weapon is None or not isinstance(weapon.content.value, str):
            raise ValueError("ordinary attack requires an exact mainhand weapon")
        entry = authority.catalog.entry(weapon.content.value)
        if entry is None or dict(entry.facts).get("damage_min") is None:
            raise ValueError("weapon damage profile is unsupported")
        facts = dict(entry.facts)
        skill_facts = dict(authority.catalog.entry(action.skill_id).facts)
        low, high = int(facts["damage_min"]), int(facts["damage_max"])
        target_states = tuple(
            product(
                _possibilities(target.resources.hit_points, "target HP"),
                _possibilities(target.resources.head_armor, "head armor"),
                _possibilities(target.resources.body_armor, "body armor"),
            )
        )
        hit = hit_chance / 100
        branches = [OutcomeBranch(HitResult.MISS, 1 - hit)]
        for location, share in ((HitResult.HEAD, 0.25), (HitResult.BODY, 0.75)):
            for damage in range(low, high + 1):
                armor_damage = int(
                    damage * float(facts.get("armor_damage_multiplier", 1))
                )
                for (hp, hp_probability), (head, head_probability), (
                    body,
                    body_probability,
                ) in target_states:
                    armor = head if location is HitResult.HEAD else body
                    direct_multiplier = float(
                        facts.get("direct_damage_multiplier", 0.3)
                    )
                    if location is HitResult.HEAD:
                        direct_multiplier += float(
                            skill_facts.get("additional_head_damage_multiplier", 0)
                        )
                    hp_damage = max(
                        0,
                        int(damage * direct_multiplier - armor * 0.1),
                    )
                    remaining = max(0, hp - hp_damage)
                    branches.append(
                        OutcomeBranch(
                            location,
                            hit
                            * share
                            / (high - low + 1)
                            * hp_probability
                            * head_probability
                            * body_probability,
                            damage,
                            armor_damage,
                            hp_damage,
                            remaining,
                            max(0, head - armor_damage)
                            if location is HitResult.HEAD
                            else head,
                            max(0, body - armor_damage)
                            if location is HitResult.BODY
                            else body,
                            remaining == 0,
                        )
                    )
        return Result.success(
            AttackOutcome(
                action.action_id,
                MODEL_VERSION,
                hit_chance,
                tuple(branches),
                epistemic=state.information_profile is InformationProfile.PLAYER_LEGAL
                and any(
                    v.representation is not Representation.EXACT
                    for v in (
                        target.resources.hit_points,
                        target.resources.head_armor,
                        target.resources.body_armor,
                    )
                ),
            )
        )
    except (StopIteration, TypeError, ValueError, KeyError) as exc:
        return Result.incomplete_coverage(
            Problem(
                ErrorCode.EVALUATION_UNSUPPORTED,
                str(exc),
                f"action_affordances.{action.action_id}",
                "ordinary_attack",
            )
        )
