"""Deterministic post-command transitions for the narrow M1 mechanics subset.

This module consumes only canonical actions resolved from TacticalState. It is
not a command generator, pathfinder, or enemy-legality engine. Contingent AOO
reactions are supplied by the fixture/future adapter and share the ordinary
attack primitive through a narrow reaction context, never a synthetic enemy
ActionAffordance.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import floor

from bb_agent.candidates import (
    CandidateReference,
    EvaluationInvalid,
    EvaluationUncertaintyUnsupported,
    EvaluationUnsupported,
    evaluation_failure_result,
    resolve_current_candidate,
)
from bb_agent.mechanics import MechanicsAuthority, ResolutionLedger, RulesStage
from bb_agent.outcomes import (
    AttackOutcome,
    HitResult,
    _AttackEvaluationContext,
    _evaluate_ordinary_attack_context,
    _reaction_attack_context,
)
from bb_agent.results import Result
from bb_agent.tactical_state import (
    ActionAffordance,
    ActionKind,
    Combatant,
    KnownValue,
    LifeState,
    Relation,
    Representation,
    TacticalState,
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
    resolution_ledgers: tuple[tuple[str, ResolutionLedger], ...] = ()


def evaluate_ordinary_attack(
    authority: MechanicsAuthority,
    state: TacticalState,
    context: _AttackEvaluationContext,
) -> AttackOutcome:
    """Internal reaction-evaluation seam; context is not an enemy affordance."""
    return _evaluate_ordinary_attack_context(authority, state, context)


def _path(action: ActionAffordance) -> str:
    return f"action_affordances.{action.action_id}"


def _unsupported(action: ActionAffordance, message: str, mechanic_id: str) -> None:
    raise EvaluationUnsupported(message, path=_path(action), mechanic_id=mechanic_id)


def _invalid(action: ActionAffordance, message: str) -> None:
    raise EvaluationInvalid(message, path=_path(action))


def _exact(value: KnownValue, name: str, action: ActionAffordance) -> int:
    if (
        value.representation is not Representation.EXACT
        or isinstance(value.value, bool)
        or not isinstance(value.value, int)
    ):
        _unsupported(action, f"{name} must be exact for this transition", "transition")
    return value.value


def _actor(state: TacticalState, action: ActionAffordance) -> Combatant:
    actor = next(
        (item for item in state.combatants if item.actor_id == action.actor_id), None
    )
    if actor is None:
        _invalid(action, "transition actor is absent from canonical state")
    return actor


def _cost_ledger(action: ActionAffordance, field: str) -> ResolutionLedger:
    try:
        ledger = ResolutionLedger.for_action_field(action, field)
    except ValueError as exc:
        _invalid(action, str(exc))
    advanced = ledger.apply(RulesStage.OUTCOME)
    if advanced.value is None:
        _invalid(action, advanced.problems[0].message)
    return advanced.value


def _with_costs(
    actor: Combatant, action: ActionAffordance
) -> tuple[Combatant, tuple[tuple[str, ResolutionLedger], ...]]:
    if action.ap_cost is None or action.fatigue_cost is None:
        _invalid(action, "transition lacks resolved AP/FAT costs")
    ledgers = (
        ("ap_cost", _cost_ledger(action, "ap_cost")),
        ("fatigue_cost", _cost_ledger(action, "fatigue_cost")),
    )
    ap = _exact(actor.resources.action_points, "actor action points", action)
    fatigue = _exact(actor.resources.fatigue, "actor fatigue", action)
    ap -= action.ap_cost.value
    fatigue += action.fatigue_cost.value
    if ap < 0 or fatigue > _exact(
        actor.resources.fatigue_capacity, "fatigue capacity", action
    ):
        _unsupported(
            action, "resolved action costs exceed actor resources", "transition"
        )
    return (
        replace(
            actor,
            resources=replace(
                actor.resources,
                action_points=KnownValue.exact(ap),
                fatigue=KnownValue.exact(fatigue),
            ),
        ),
        ledgers,
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
        _unsupported(action, "mover position must be exact for movement", "move")
    matches = [
        index
        for index, tile_id in enumerate(action.resolved_path)
        if tile_id == path_step_tile_id
    ]
    if len(matches) != 1:
        _unsupported(
            action, "reaction trigger must identify one unique path step", "aoo"
        )
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
            _unsupported(action, "duplicate contingent AOO reaction", "aoo")
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
            _unsupported(
                action, "contingent AOO reactor is not a known living hostile", "aoo"
            )
        origin = tiles.get(origin_tile_id)
        if origin is None:
            _invalid(action, "reaction trigger origin is absent from canonical map")
        if reactor.position.value not in {
            neighbor for neighbor in origin.neighbors if neighbor is not None
        }:
            _unsupported(
                action,
                "contingent AOO reactor is not adjacent to trigger origin",
                "aoo",
            )


def _unwrap_reaction_attack(
    action: ActionAffordance,
    evaluated: AttackOutcome | Result[AttackOutcome],
) -> AttackOutcome:
    """Accept the historical Result-returning test seam without hiding failures."""
    if isinstance(evaluated, Result):
        if evaluated.value is None:
            problem = evaluated.problems[0]
            if problem.code.value == "VALIDATION_FAILED":
                raise EvaluationInvalid(problem.message, path=_path(action))
            raise EvaluationUnsupported(
                problem.message,
                path=_path(action),
                mechanic_id=problem.mechanic_id or "ordinary_attack",
            )
        return evaluated.value
    return evaluated


def _move(
    authority: MechanicsAuthority, state: TacticalState, action: ActionAffordance
) -> TransitionOutcome:
    mover = _actor(state, action)
    _validate_reaction_geometry(state, mover, action)

    if action.contingent_reactions and len(action.resolved_path) != 1:
        _unsupported(
            action,
            "contingent AOO on multi-step movement requires per-step resolved costs",
            "move",
        )

    if action.contingent_reactions:
        if mover.position.representation is not Representation.EXACT or not isinstance(
            mover.position.value, str
        ):
            _unsupported(action, "mover position must be exact for movement", "move")
        origin_tile_id = mover.position.value
        paid, ledgers = _with_costs(mover, action)
        reaction_ledgers: dict[str, ResolutionLedger] = {}
        # Battle Brothers resolves disengagement while the mover is attempting to
        # leave the controlled hex. All applicable supplied reactions may resolve;
        # any hit interrupts the step, while only the all-miss branch reaches the
        # destination. Death suppresses later reactions.
        pending = [(1.0, paid, False, ())]
        for reaction in sorted(
            action.contingent_reactions,
            key=lambda item: item.reacting_actor_id,
        ):
            context = _reaction_attack_context(
                action.action_id, reaction, mover.actor_id
            )
            prefix = (
                f"aoo:{reaction.path_step_tile_id}:" f"{reaction.reacting_actor_id}"
            )
            for name, ledger in context.resolution_ledgers:
                scoped_name = f"{prefix}.{name}"
                prior = reaction_ledgers.get(scoped_name)
                if prior is not None and prior != ledger:
                    _invalid(action, "reaction resolution provenance changed by branch")
                reaction_ledgers[scoped_name] = ledger
            next_pending = []
            for probability, actor, interrupted, effects in pending:
                if actor.life_state is not LifeState.ALIVE:
                    next_pending.append((probability, actor, True, effects))
                    continue
                variant = replace(
                    state,
                    combatants=tuple(
                        actor if item.actor_id == actor.actor_id else item
                        for item in state.combatants
                    ),
                )
                try:
                    evaluated = evaluate_ordinary_attack(authority, variant, context)
                except EvaluationUncertaintyUnsupported:
                    _unsupported(
                        action,
                        "contingent AOO cannot represent its outcome uncertainty",
                        "aoo",
                    )
                attack = _unwrap_reaction_attack(action, evaluated)
                if (
                    attack.epistemic
                    or attack.epistemic_scenarios
                    or not attack.branches
                ):
                    _unsupported(
                        action,
                        "contingent AOO cannot represent its outcome uncertainty",
                        "aoo",
                    )
                for branch in attack.branches:
                    hit = branch.result is not HitResult.MISS
                    if (
                        branch.target_hp is None
                        or branch.target_head_armor is None
                        or branch.target_body_armor is None
                    ):
                        _invalid(
                            action, "contingent AOO returned incomplete target state"
                        )
                    updated = replace(
                        actor,
                        resources=replace(
                            actor.resources,
                            hit_points=KnownValue.exact(branch.target_hp),
                            head_armor=KnownValue.exact(int(branch.target_head_armor)),
                            body_armor=KnownValue.exact(int(branch.target_body_armor)),
                        ),
                        life_state=(
                            LifeState.REMOVED if branch.killed else actor.life_state
                        ),
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
            ledgers + tuple(sorted(reaction_ledgers.items())),
        )

    moved, ledgers = _with_costs(mover, action)
    moved = replace(moved, position=KnownValue.exact(action.destination_tile_id))
    return TransitionOutcome(
        action.action_id,
        MODEL_VERSION,
        (TransitionBranch(1.0, True, False, moved, action.destination_tile_id),),
        ledgers,
    )


def _simple(state: TacticalState, action: ActionAffordance) -> TransitionOutcome:
    actor, ledgers = _with_costs(_actor(state, action), action)
    outcome_ledgers = list(ledgers)
    effects: tuple[tuple[str, object], ...] = ()
    waited: bool | None = None
    may_wait: bool | None = None
    ended = False
    if action.kind is ActionKind.WAIT:
        waited, may_wait = True, False
    elif action.kind is ActionKind.END_TURN:
        ended = True
    elif action.skill_id == "actives.recover":
        fatigue = floor(
            _exact(actor.resources.fatigue, "actor fatigue", action) / 2 + 0.5
        )
        actor = replace(
            actor, resources=replace(actor.resources, fatigue=KnownValue.exact(fatigue))
        )
        effects = (("fatigue_recovered", True),)
    elif action.skill_id == "actives.reload_bolt":
        if action.ammo_cost is None:
            _invalid(action, "reload lacks resolved ammo cost")
        outcome_ledgers.append(("ammo_cost", _cost_ledger(action, "ammo_cost")))
        effects = (("loaded", True), ("ammo_consumed", action.ammo_cost.value))
    elif action.kind is ActionKind.EQUIP_ITEM:
        item = next(
            (item for item in actor.equipment if item.item_id == action.item_id), None
        )
        if item is None:
            _invalid(action, "equipment source item is absent from canonical actor")
        if (
            item.slot.representation is not Representation.EXACT
            or item.slot.value != action.source_location
        ):
            _unsupported(action, "equipment source location is not exact", "equip")
        equipped = replace(item, slot=KnownValue.exact(action.target_slot))
        displaced = None
        if action.displaced_item_id is not None:
            displaced = next(
                (
                    candidate
                    for candidate in actor.equipment
                    if candidate.item_id == action.displaced_item_id
                ),
                None,
            )
            if displaced is None:
                _invalid(action, "displaced item is absent from canonical actor")
            if (
                displaced.slot.representation is not Representation.EXACT
                or displaced.slot.value != action.target_slot
            ):
                _unsupported(
                    action, "displaced item is not in the target slot", "equip"
                )
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
        _unsupported(action, "unsupported deterministic transition", "transition")
    return TransitionOutcome(
        action.action_id,
        MODEL_VERSION,
        (
            TransitionBranch(
                1.0, True, False, actor, None, waited, may_wait, ended, effects
            ),
        ),
        tuple(outcome_ledgers),
    )


def evaluate_transition(
    authority: MechanicsAuthority,
    state: TacticalState,
    action: CandidateReference,
) -> Result[TransitionOutcome]:
    """Evaluate one canonical current transition and preserve failure classes.

    Legacy callers may pass an ActionAffordance reference, but only its action_id is
    consumed; all transition fields are resolved from normalized TacticalState.
    """

    candidate = resolve_current_candidate(authority, state, action)
    if candidate.value is None:
        return Result(candidate.status, problems=candidate.problems)
    try:
        outcome = (
            _move(authority, candidate.value.state, candidate.value.action)
            if candidate.value.action.kind is ActionKind.MOVE_TO
            else _simple(candidate.value.state, candidate.value.action)
        )
        return Result.success(outcome)
    except (EvaluationUnsupported, EvaluationInvalid) as exc:
        return evaluation_failure_result(exc)
