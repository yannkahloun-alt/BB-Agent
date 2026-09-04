"""Deterministic post-command transitions for the narrow M1 mechanics subset.

This module deliberately consumes only an already supplied affordance.  It is
not a command generator or pathfinder.  AOO-capable paths are detected from
the canonical path/state and fail closed until an attacker-specific outcome
primitive can be supplied by the catalog.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import floor

from bb_agent.mechanics import CoverageStatus, MechanicsAuthority
from bb_agent.outcomes import evaluate_ordinary_attack
from bb_agent.results import ErrorCode, Problem, Result
from bb_agent.tactical_state import (
    ActionAffordance,
    ActionKind,
    Combatant,
    KnownValue,
    LifeState,
    PlayerVisiblePreview,
    Representation,
    ResolutionStage,
    ResolvedCost,
    TacticalState,
    TargetKind,
)

MODEL_VERSION = "transitions.v1"


@dataclass(frozen=True, slots=True)
class TransitionBranch:
    """A deterministic post-command branch, ready for later risk evaluation."""

    probability: float
    completed: bool
    interrupted: bool
    actor: Combatant
    destination_tile_id: str | None
    actor_has_waited: bool | None = None
    actor_may_wait: bool | None = None
    turn_ended: bool = False
    effects: tuple[tuple[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class TransitionOutcome:
    action_id: str
    model_version: str
    branches: tuple[TransitionBranch, ...]


def _exact(value: KnownValue, name: str) -> int:
    if (
        value.representation is not Representation.EXACT
        or isinstance(value.value, bool)
        or not isinstance(value.value, int)
    ):
        raise ValueError(f"{name} must be exact for this transition")
    return value.value


def _actor(state: TacticalState, action: ActionAffordance) -> Combatant:
    return next(
        actor for actor in state.combatants if actor.actor_id == action.actor_id
    )


def _with_costs(actor: Combatant, action: ActionAffordance) -> Combatant:
    ap = (
        _exact(actor.resources.action_points, "actor action points")
        - action.ap_cost.value
    )
    fatigue = (
        _exact(actor.resources.fatigue, "actor fatigue") + action.fatigue_cost.value
    )
    if ap < 0 or fatigue > _exact(actor.resources.fatigue_capacity, "fatigue capacity"):
        raise ValueError("resolved action costs exceed actor resources")
    return replace(
        actor,
        resources=replace(
            actor.resources,
            action_points=KnownValue.exact(ap),
            fatigue=KnownValue.exact(fatigue),
        ),
    )


def _hostile_zoc(
    state: TacticalState, mover: Combatant, tile_id: str
) -> tuple[str, ...]:
    tile = next(tile for tile in state.tiles if tile.tile_id == tile_id)
    adjacent = {neighbor for neighbor in tile.neighbors if neighbor is not None}
    return tuple(
        actor.actor_id
        for actor in state.combatants
        if actor.relation.value == "HOSTILE"
        and actor.life_state is LifeState.ALIVE
        and actor.position.representation is Representation.EXACT
        and actor.position.value in adjacent
    )


def _move_aoo_attackers(
    state: TacticalState, mover: Combatant, action: ActionAffordance
) -> tuple[str, ...]:
    if mover.position.representation is not Representation.EXACT or not isinstance(
        mover.position.value, str
    ):
        raise ValueError("mover position must be exact for movement")
    previous = mover.position.value
    attackers: set[str] = set()
    for step in action.resolved_path:
        leaving = set(_hostile_zoc(state, mover, previous))
        arriving = set(_hostile_zoc(state, mover, step))
        attackers.update(leaving - arriving)
        previous = step
    return tuple(sorted(attackers))


def _move(
    authority: MechanicsAuthority, state: TacticalState, action: ActionAffordance
) -> TransitionOutcome:
    mover = _actor(state, action)
    attackers = _move_aoo_attackers(state, mover, action)
    supplied = {reaction.reacting_actor_id for reaction in action.contingent_reactions}
    if set(attackers) != supplied:
        raise ValueError("AOO trigger/reaction context mismatch")
    if any(
        reaction.unsupported_mechanic_id for reaction in action.contingent_reactions
    ):
        raise ValueError("unsupported contingent AOO mechanic")
    if action.contingent_reactions:
        if len(action.contingent_reactions) != 1:
            raise ValueError("multiple contingent AOO reactions are unsupported")
        reaction = action.contingent_reactions[0]
        zero = ResolvedCost(
            0, ResolutionStage.PREVIEW_RESOLVED, action.ap_cost.authority
        )
        synthetic = ActionAffordance(
            "contingent-aoo",
            reaction.reacting_actor_id,
            ActionKind.USE_SKILL,
            action.provenance,
            action.source_generation,
            ap_cost=zero,
            fatigue_cost=zero,
            charge_cost=zero,
            ammo_cost=zero,
            item_action_cost=zero,
            skill_id=reaction.skill_id,
            target_kind=TargetKind.ACTOR,
            target_actor_id=mover.actor_id,
            preview=PlayerVisiblePreview(displayed_hit_chance=reaction.hit_chance),
        )
        attack = evaluate_ordinary_attack(authority, state, synthetic)
        if attack.value is None:
            raise ValueError("contingent AOO is outside ordinary attack coverage")
        moved = replace(_with_costs(mover, action))

        def post_aoo(branch):
            resources = replace(
                moved.resources,
                hit_points=KnownValue.exact(branch.target_hp),
                head_armor=KnownValue.exact(int(branch.target_head_armor)),
                body_armor=KnownValue.exact(int(branch.target_body_armor)),
            )
            return replace(
                moved,
                resources=resources,
                life_state=LifeState.REMOVED if branch.killed else moved.life_state,
                position=KnownValue.exact(
                    reaction.path_step_tile_id
                    if branch.killed
                    else action.destination_tile_id
                ),
            )

        return TransitionOutcome(
            action.action_id,
            MODEL_VERSION,
            tuple(
                TransitionBranch(
                    branch.probability,
                    not branch.killed,
                    branch.killed,
                    post_aoo(branch),
                    action.destination_tile_id
                    if not branch.killed
                    else reaction.path_step_tile_id,
                    effects=(
                        ("aoo", reaction.reacting_actor_id),
                        ("hp_damage", branch.hp_damage),
                    ),
                )
                for branch in attack.value.branches
            ),
        )
    moved = replace(
        _with_costs(mover, action),
        position=KnownValue.exact(action.destination_tile_id),
    )
    return TransitionOutcome(
        action.action_id,
        MODEL_VERSION,
        (TransitionBranch(1.0, True, False, moved, action.destination_tile_id),),
    )


def _simple(state: TacticalState, action: ActionAffordance) -> TransitionOutcome:
    actor = _with_costs(_actor(state, action), action)
    effects: tuple[tuple[str, object], ...] = ()
    waited: bool | None = None
    may_wait: bool | None = None
    ended = False
    if action.kind is ActionKind.WAIT:
        waited, may_wait = True, False
    elif action.kind is ActionKind.END_TURN:
        ended = True
    elif action.skill_id == "actives.recover":
        fatigue = floor(_exact(actor.resources.fatigue, "actor fatigue") / 2 + 0.5)
        actor = replace(
            actor, resources=replace(actor.resources, fatigue=KnownValue.exact(fatigue))
        )
        effects = (("fatigue_recovered", True),)
    elif action.skill_id == "actives.reload_bolt":
        effects = (("loaded", True), ("ammo_consumed", action.ammo_cost.value))
    elif action.kind is ActionKind.EQUIP_ITEM:
        item = next(item for item in actor.equipment if item.item_id == action.item_id)
        if (
            item.slot.representation is not Representation.EXACT
            or item.slot.value != action.source_location
        ):
            raise ValueError("equipment source location is not exact")
        equipped = replace(item, slot=KnownValue.exact(action.target_slot))
        actor = replace(
            actor,
            equipment=tuple(
                equipped if candidate.item_id == item.item_id else candidate
                for candidate in actor.equipment
            ),
        )
        effects = (("equipped_item_id", item.item_id),)
    else:
        raise ValueError("unsupported deterministic transition")
    return TransitionOutcome(
        action.action_id,
        MODEL_VERSION,
        (
            TransitionBranch(
                1.0, True, False, actor, None, waited, may_wait, ended, effects
            ),
        ),
    )


def evaluate_transition(
    authority: MechanicsAuthority, state: TacticalState, action: ActionAffordance
) -> Result[TransitionOutcome]:
    """Evaluate one declared transition; reject unsupported mechanics visibly."""
    try:
        coverage = authority.classify(state)
        item = next(
            entry
            for entry in coverage.value.affordances
            if entry.action_id == action.action_id
        )
        if item.status is not CoverageStatus.SUPPORTED:
            raise ValueError("action is not covered by the active manifest")
        outcome = (
            _move(authority, state, action)
            if action.kind is ActionKind.MOVE_TO
            else _simple(state, action)
        )
        return Result.success(outcome)
    except (AttributeError, StopIteration, TypeError, ValueError) as exc:
        return Result.incomplete_coverage(
            Problem(
                ErrorCode.EVALUATION_UNSUPPORTED,
                str(exc),
                f"action_affordances.{action.action_id}",
                "transition",
            )
        )
