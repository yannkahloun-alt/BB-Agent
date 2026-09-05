"""Deterministic outcomes for the catalog-declared ordinary attack family."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from itertools import product

from bb_agent.candidates import (
    CandidateReference,
    EvaluationInvalid,
    EvaluationUncertaintyUnsupported,
    EvaluationUnsupported,
    evaluation_failure_result,
    resolve_current_candidate,
)
from bb_agent.mechanics import (
    CoverageStatus,
    MechanicsAuthority,
    ResolutionLedger,
    RulesStage,
)
from bb_agent.results import Result
from bb_agent.tactical_state import (
    ActionAffordance,
    ActionKind,
    ContingentReaction,
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
    resolution_ledgers: tuple[tuple[str, ResolutionLedger], ...] = ()

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


@dataclass(frozen=True, slots=True)
class _AttackEvaluationContext:
    """Small shared input for current attacks and supplied contingent reactions."""

    evaluation_id: str
    problem_path: str
    attacker_id: str
    target_actor_id: str
    skill_id: str
    hit_chance: int
    actor_action_points: int | None
    actor_fatigue: int | None
    resolution_ledgers: tuple[tuple[str, ResolutionLedger], ...]

    @property
    def actor_id(self) -> str:
        """Compatibility name used by the existing transition test seam."""
        return self.attacker_id


def _unsupported(message: str, context: _AttackEvaluationContext | str) -> None:
    path = (
        context.problem_path
        if isinstance(context, _AttackEvaluationContext)
        else context
    )
    raise EvaluationUnsupported(message, path=path, mechanic_id="ordinary_attack")


def _invalid(message: str, path: str) -> None:
    raise EvaluationInvalid(message, path=path)


def _exact(value, label: str, path: str) -> int:
    if (
        value is None
        or value.representation is not Representation.EXACT
        or isinstance(value.value, bool)
        or not isinstance(value.value, int)
    ):
        raise EvaluationUnsupported(
            f"{label} must be exact for this outcome model",
            path=path,
            mechanic_id="ordinary_attack",
        )
    return value.value


def _values(value, label: str, path: str) -> tuple[tuple[int, float | None], ...]:
    """Return a justified distribution or an unweighted robustness domain."""
    if value.representation is Representation.EXACT:
        return ((_exact(value, label, path), 1.0),)
    if value.representation is Representation.DISTRIBUTION:
        if not all(
            isinstance(item, int) and not isinstance(item, bool)
            for item, _ in value.distribution
        ):
            _unsupported(f"{label} distribution must contain integers", path)
        return tuple((item, probability) for item, probability in value.distribution)
    if value.representation is Representation.SET:
        if not all(
            isinstance(item, int) and not isinstance(item, bool)
            for item in value.candidates
        ):
            _unsupported(f"{label} set must contain integers", path)
        return tuple((item, None) for item in sorted(value.candidates))
    if value.representation is Representation.RANGE:
        if not isinstance(value.minimum, int) or not isinstance(value.maximum, int):
            _unsupported(f"{label} range must have integer endpoints", path)
        return tuple((item, None) for item in range(value.minimum, value.maximum + 1))
    raise EvaluationUncertaintyUnsupported(
        f"{label} is unknown and cannot be evaluated",
        path=path,
        mechanic_id="ordinary_attack",
    )


def _advance_ledger(
    ledger: ResolutionLedger, stage: RulesStage, path: str
) -> ResolutionLedger:
    advanced = ledger.apply(stage)
    if advanced.value is None:
        problem = advanced.problems[0]
        _invalid(problem.message, path)
    return advanced.value


def _resolved_ledger(value, stage: RulesStage, path: str) -> ResolutionLedger:
    try:
        ledger = ResolutionLedger.from_resolved(value, stage)
    except ValueError as exc:
        _invalid(str(exc), path)
    return _advance_ledger(ledger, RulesStage.OUTCOME, path)


def _action_ledger(action: ActionAffordance, field: str, path: str) -> ResolutionLedger:
    try:
        ledger = ResolutionLedger.for_action_field(action, field)
    except ValueError as exc:
        _invalid(str(exc), path)
    return _advance_ledger(ledger, RulesStage.OUTCOME, path)


def _current_attack_context(
    state: TacticalState, action: ActionAffordance
) -> _AttackEvaluationContext:
    path = f"action_affordances.{action.action_id}"
    if action.kind is not ActionKind.USE_SKILL or action.skill_id != "actives.chop":
        raise EvaluationUnsupported(
            "action is not a supported ordinary attack",
            path=path,
            mechanic_id="ordinary_attack",
        )
    if action.target_actor_id is None:
        _invalid("ordinary attack has no target actor", path)
    preview = action.preview.displayed_hit_chance
    if preview is None or isinstance(preview.value, bool) or not isinstance(
        preview.value, int
    ):
        raise EvaluationUnsupported(
            "ordinary attack requires an integer displayed hit chance",
            path=path,
            mechanic_id="ordinary_attack",
        )
    if not 5 <= preview.value <= 95:
        raise EvaluationUnsupported(
            "ordinary attack requires a capped player-visible hit chance",
            path=path,
            mechanic_id="ordinary_attack",
        )
    actor = next(
        (item for item in state.combatants if item.actor_id == action.actor_id), None
    )
    if actor is None:
        _invalid("ordinary attack actor is absent from canonical state", path)
    if action.ap_cost is None or action.fatigue_cost is None:
        _invalid("ordinary attack lacks resolved AP/FAT costs", path)
    actor_ap = _exact(actor.resources.action_points, "actor action points", path)
    actor_fatigue = _exact(actor.resources.fatigue, "actor fatigue", path)
    actor_ap -= action.ap_cost.value
    actor_fatigue += action.fatigue_cost.value
    fatigue_capacity = _exact(
        actor.resources.fatigue_capacity, "actor fatigue capacity", path
    )
    if actor_ap < 0 or actor_fatigue > fatigue_capacity:
        _invalid("resolved action costs exceed actor resources", path)
    return _AttackEvaluationContext(
        action.action_id,
        path,
        action.actor_id,
        action.target_actor_id,
        action.skill_id,
        preview.value,
        actor_ap,
        actor_fatigue,
        (
            ("ap_cost", _action_ledger(action, "ap_cost", path)),
            ("fatigue_cost", _action_ledger(action, "fatigue_cost", path)),
            (
                "displayed_hit_chance",
                _action_ledger(action, "displayed_hit_chance", path),
            ),
        ),
    )


def _reaction_attack_context(
    move_action_id: str,
    reaction: ContingentReaction,
    target_actor_id: str,
) -> _AttackEvaluationContext:
    path = f"action_affordances.{move_action_id}.contingent_reactions"
    if reaction.unsupported_mechanic_id is not None:
        raise EvaluationUnsupported(
            "unsupported contingent AOO mechanic",
            path=path,
            mechanic_id=reaction.unsupported_mechanic_id,
        )
    if reaction.skill_id is None or reaction.hit_chance is None:
        raise EvaluationUnsupported(
            "contingent AOO lacks supported attack inputs",
            path=path,
            mechanic_id="ordinary_attack",
        )
    hit = reaction.hit_chance.value
    if isinstance(hit, bool) or not isinstance(hit, int) or not 5 <= hit <= 95:
        raise EvaluationUnsupported(
            "ordinary attack requires a capped player-visible hit chance",
            path=path,
            mechanic_id="ordinary_attack",
        )
    return _AttackEvaluationContext(
        (
            f"{move_action_id}:aoo:{reaction.path_step_tile_id}:"
            f"{reaction.reacting_actor_id}"
        ),
        path,
        reaction.reacting_actor_id,
        target_actor_id,
        reaction.skill_id,
        hit,
        None,
        None,
        (
            (
                "displayed_hit_chance",
                _resolved_ledger(
                    reaction.hit_chance, RulesStage.CURRENT_HIT_CHANCE, path
                ),
            ),
        ),
    )


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
    actor_ap: int | None,
    actor_fatigue: int | None,
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


def _evaluate_ordinary_attack_context(
    authority: MechanicsAuthority,
    state: TacticalState,
    context: _AttackEvaluationContext,
) -> AttackOutcome:
    family = authority.manifest.family("ordinary_attack")
    if family.status is not CoverageStatus.SUPPORTED:
        _unsupported("ordinary attack is not covered by the active manifest", context)
    actor = next(
        (item for item in state.combatants if item.actor_id == context.attacker_id),
        None,
    )
    target = next(
        (item for item in state.combatants if item.actor_id == context.target_actor_id),
        None,
    )
    if actor is None or target is None:
        _invalid(
            "ordinary attack actor or target is absent from canonical state",
            context.problem_path,
        )
    if actor.effects or target.effects or target.equipment:
        _unsupported(
            "ordinary attack has unmodelled effects or target equipment", context
        )
    for combatant in (actor, target):
        if (
            combatant.perks.representation is not Representation.EXACT
            or combatant.perks.value not in ((), [])
            or combatant.traits.representation is not Representation.EXACT
            or combatant.traits.value not in ((), [])
        ):
            _unsupported("ordinary attack has unmodelled perks or traits", context)
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
        _unsupported("ordinary attack requires an exact mainhand weapon", context)
    if len(actor.equipment) != 1:
        _unsupported("ordinary attack has unmodelled actor equipment", context)
    weapon_entry = authority.catalog.entry(weapon.content.value)
    skill_entry = authority.catalog.entry(context.skill_id)
    if (
        weapon.content.value != "weapon.hand_axe"
        or weapon_entry is None
        or skill_entry is None
        or skill_entry.family_id != "ordinary_attack"
    ):
        _unsupported("weapon or skill damage profile is unsupported", context)
    weapon_facts, skill_facts = dict(weapon_entry.facts), dict(skill_entry.facts)
    if "damage_min" not in weapon_facts:
        _unsupported("weapon damage profile is unsupported", context)
    kwargs = dict(
        hit_chance=context.hit_chance,
        low=int(weapon_facts["damage_min"]),
        high=int(weapon_facts["damage_max"]),
        armor_multiplier=float(weapon_facts["armor_damage_multiplier"]),
        direct_multiplier=float(skill_facts["direct_damage_multiplier"]),
        head_multiplier=1 + float(skill_facts["additional_head_damage_multiplier"]),
        actor_ap=context.actor_action_points,
        actor_fatigue=context.actor_fatigue,
    )
    integrated: list[OutcomeBranch] = []
    scenarios: list[EpistemicScenario] = []
    for (hp, hp_probability), (head, head_probability), (
        body,
        body_probability,
    ) in product(
        _values(target.resources.hit_points, "target HP", context.problem_path),
        _values(target.resources.head_armor, "head armor", context.problem_path),
        _values(target.resources.body_armor, "body armor", context.problem_path),
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
        _unsupported(
            "mixed weighted and envelope target knowledge is unsupported", context
        )
    return AttackOutcome(
        context.evaluation_id,
        MODEL_VERSION,
        context.hit_chance,
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
        resolution_ledgers=context.resolution_ledgers,
    )


def evaluate_ordinary_attack(
    authority: MechanicsAuthority,
    state: TacticalState,
    action: CandidateReference,
) -> Result[AttackOutcome]:
    """Evaluate the canonical current ordinary attack identified by action_id.

    Legacy callers may pass an ActionAffordance reference, but only its action_id is
    consumed; every executable field is re-resolved from normalized TacticalState.
    """

    candidate = resolve_current_candidate(authority, state, action)
    if candidate.value is None:
        return Result(candidate.status, problems=candidate.problems)
    try:
        context = _current_attack_context(candidate.value.state, candidate.value.action)
        return Result.success(
            _evaluate_ordinary_attack_context(authority, candidate.value.state, context)
        )
    except (EvaluationUnsupported, EvaluationInvalid) as exc:
        return evaluation_failure_result(exc)
