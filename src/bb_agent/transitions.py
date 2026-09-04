"""Deterministic post-command transitions for the narrow M1 mechanics subset.

This module deliberately consumes only an already supplied affordance. It is
not a command generator, pathfinder, or enemy-legality engine. Contingent AOO
reactions are supplied by the fixture/future adapter and are validated here only
against the canonical path and actor geometry needed to resolve the transition.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import floor

from bb_agent.mechanics import CoverageStatus, MechanicsAuthority
from bb_agent.outcomes import HitResult, evaluate_ordinary_attack
from bb_agent.results import ErrorCode, Problem, Result
from bb_agent.tactical_state import (
    ActionAffordance,
    ActionKind,
    Combatant,
    KnownValue,
    LifeState,
    PlayerVisiblePreview,
    Relation,
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


def _reaction_origin_tile(
    state: TacticalState,
    mover: Combatant,
    action: ActionAffordance,
    path_step_tile_id: str,
) -> str:
    """Return the tile the mover is attempting to leave for one supplied reaction."""
    if mover.position.representation is not Representation.EXACT or not isinstance(
        mover.position.value, str
    ):
        raise ValueError("mover position must be exact for movement")
    matches = [
        index
        for index, tile_id in enumerate(action.resolved_path)
        if tile_id == path_step_tile_id
    ]
    if len(matches) != 1:
        raise ValueError("reaction trigger must identify one unique path step")
    index = matches[0]
    return mover.position.value if index == 0 else action.resolved_path[index - 1]


def _validate_reaction_geometry(
    state: TacticalState,
    mover: Combatant,
    action: ActionAffordance,
) -> None:
    seen: set[tuple[str, str]] = set()
    actors = {actor.actor_id: actor for actor in state.combatants}
    tiles = {tile.tile_id: tile for tile in state.tiles}
    for reaction in action.contingent_reactions:
        identity = (reaction.path_step_tile_id, reaction.reacting_actor_id)
        if identity in seen:
            raise ValueError("duplicate contingent AOO reaction")
        seen.add(identity)
        origin_tile_id = _reaction_origin_tile(
            state, mover, action, reaction.path_step_tile_id
        )
        reactor = actors.get(reaction.reacting_actor_id)
        if (
            reactor is None
            or reactor.relation is not Relation.HOSTILE
            or reactor.life_state is not LifeState.ALIVE
            or reactor.position.representation is not Representation.EXACT
            or not isinstance(reactor.position.value, str)
        ):
            raise ValueError("contingent AOO reactor is not a known living hostile")
        if reactor.position.value not in {
            neighbor
            for neighbor in tiles[origin_tile_id].neighbors
            if neighbor is not None
        }:
            raise ValueError("contingent AOO reactor is not adjacent to trigger origin")


def _move(
    authority: MechanicsAuthority, state: TacticalState, action: ActionAffordance
) -> TransitionOutcome:
    mover = _actor(state, action)
    _validate_reaction_geometry(state, mover, action)
    if any(
        reaction.unsupported_mechanic_id for reaction in action.contingent_reactions
    ):
        raise ValueError("unsupported contingent AOO mechanic")

    if action.contingent_reactions and len(action.resolved_path) != 1:
        raise ValueError(
            "contingent AOO on multi-step movement requires per-step resolved costs"
        )

    if action.contingent_reactions:
        if mover.position.representation is not Representation.EXACT or not isinstance(
            mover.position.value, str
        ):
            raise ValueError("mover position must be exact for movement")
        origin_tile_id = mover.position.value
        zero = ResolvedCost(
            0, ResolutionStage.PREVIEW_RESOLVED, action.ap_cost.authority
        )
        paid = _with_costs(mover, action)
        # Battle Brothers resolves disengagement while the mover is attempting to
        # leave the controlled hex. All applicable reactions on that attempt may
        # resolve; any hit interrupts the step, while only the all-miss branch
        # reaches the destination. Death suppresses later reactions.
        pending = [(1.0, paid, False, ())]
        for reaction in sorted(
            action.contingent_reactions,
            key=lambda item: item.reacting_actor_id,
        ):
            next_pending = []
            for probability, actor, interrupted, effects in pending:
                if actor.life_state is not LifeState.ALIVE:
                    next_pending.append((probability, actor, True, effects))
                    continue
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
                    preview=PlayerVisiblePreview(
                        displayed_hit_chance=reaction.hit_chance
                    ),
                )
                variant = replace(
                    state,
                    combatants=tuple(
                        actor if item.actor_id == actor.actor_id else item
                        for item in state.combatants
                    ),
                )
                attack = evaluate_ordinary_attack(authority, variant, synthetic)
                if (
                    attack.value is None
                    or attack.value.epistemic
                    or attack.value.epistemic_scenarios
                    or not attack.value.branches
                ):
                    raise ValueError(
                        "contingent AOO cannot represent its outcome uncertainty"
                    )
                for branch in attack.value.branches:
                    hit = branch.result is not HitResult.MISS
                    updated = replace(
                        actor,
                        resources=replace(
                            actor.resources,
                            hit_points=KnownValue.exact(branch.target_hp),
                            head_armor=KnownValue.exact(int(branch.target_head_armor)),
                            body_armor=KnownValue.exact(int(branch.target_body_armor)),
                        ),
                        life_state=LifeState.REMOVED
                        if branch.killed
                        else actor.life_state,
                    )
                    next_pending.append(
                        (
                            probability * branch.probability,
                            updated,
                            interrupted or hit,
                            effects
                            + (
                                ("aoo", reaction.reacting_actor_id),
                                ("aoo_result", branch.result.value),
                                ("hp_damage", branch.hp_damage),
                            ),
                        )
                    )
            pending = next_pending
        return TransitionOutcome(
            action.action_id,
            MODEL_VERSION,
            tuple(
                TransitionBranch(
                    probability,
                    actor.life_state is LifeState.ALIVE and not interrupted,
                    interrupted or actor.life_state is not LifeState.ALIVE,
                    replace(
                        actor, position=KnownValue.exact(action.destination_tile_id)
                    )
                    if actor.life_state is LifeState.ALIVE and not interrupted
                    else replace(actor, position=KnownValue.exact(origin_tile_id)),
                    action.destination_tile_id
                    if actor.life_state is LifeState.ALIVE and not interrupted
                    else origin_tile_id,
                    effects=effects,
                )
                for probability, actor, interrupted, effects in pending
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
        displaced = None
        if action.displaced_item_id is not None:
            displaced = next(
                candidate
                for candidate in actor.equipment
                if candidate.item_id == action.displaced_item_id
            )
            if (
                displaced.slot.representation is not Representation.EXACT
                or displaced.slot.value != action.target_slot
            ):
                raise ValueError("displaced item is not in the target slot")
            displaced = replace(
                displaced, slot=KnownValue.exact(action.displaced_item_destination)
            )
        actor = replace(
            actor,
            equipment=tuple(
                equipped
                if candidate.item_id == item.item_id
                else displaced
                if displaced is not None and candidate.item_id == displaced.item_id
                else candidate
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
