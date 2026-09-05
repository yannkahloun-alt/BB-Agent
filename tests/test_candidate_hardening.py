from dataclasses import fields, replace

import pytest

import bb_agent.outcomes as outcomes
import bb_agent.transitions as transitions
from bb_agent.mechanics import MechanicsAuthority
from bb_agent.outcomes import evaluate_ordinary_attack
from bb_agent.results import ErrorCode, ResultStatus
from bb_agent.tactical_state import (
    ActionAffordance,
    AffordanceProvenance,
    EffectState,
    KnownValue,
    ResolutionAuthority,
    ResolutionStage,
    TacticalState,
)
from bb_agent.transitions import evaluate_transition
from test_mechanics import (
    _attack,
    _authority,
    _move_action,
    _movement_state,
    _ordinary_attack_state,
    _reaction,
    _resource_action,
    _snapshot,
    _wait,
)
from test_tactical_state import _state


def _with_actions(state: TacticalState, *actions, **changes) -> TacticalState:
    values = {field.name: getattr(state, field.name) for field in fields(state)}
    values.update(
        state_id="",
        action_affordances=replace(state.action_affordances, actions=actions),
    )
    values.update(changes)
    return TacticalState.create(**values)


def test_attack_evaluation_resolves_canonical_action_not_divergent_copy():
    authority = _authority()
    state = _ordinary_attack_state(authority)
    action = state.action_affordances.actions[0]
    divergent = replace(
        action,
        ap_cost=replace(action.ap_cost, value=9),
        fatigue_cost=replace(action.fatigue_cost, value=90),
        preview=replace(
            action.preview,
            displayed_hit_chance=replace(action.preview.displayed_hit_chance, value=95),
        ),
    )

    result = evaluate_ordinary_attack(authority, state, divergent)

    assert result.status is ResultStatus.SUCCESS
    assert result.value is not None
    assert result.value.hit_chance == 67
    assert result.value.branches[0].actor_action_points == 5
    assert result.value.branches[0].actor_fatigue == 10


def test_transition_evaluation_resolves_canonical_action_not_divergent_copy():
    authority = _authority()
    state = _snapshot(authority, _wait())
    action = state.action_affordances.actions[0]
    divergent = replace(action, ap_cost=replace(action.ap_cost, value=9))

    result = evaluate_transition(authority, state, divergent)

    assert result.status is ResultStatus.SUCCESS
    assert result.value is not None
    assert result.value.branches[0].actor.resources.action_points.value == 9


def test_unknown_action_id_and_stale_state_are_validation_failures():
    authority = _authority()
    state = _snapshot(authority, _wait())

    unknown = evaluate_transition(authority, state, "action:not-current")
    assert unknown.status is ResultStatus.VALIDATION_FAILURE
    assert unknown.problems[0].code is ErrorCode.VALIDATION_FAILED

    stale = replace(state, state_id="stale")
    stale_result = evaluate_transition(
        authority, stale, state.action_affordances.actions[0].action_id
    )
    assert stale_result.status is ResultStatus.VALIDATION_FAILURE
    assert stale_result.problems[0].code is ErrorCode.VALIDATION_FAILED


def test_structural_and_concrete_evaluation_failures_are_distinct():
    authority = _authority()
    structural_state = _snapshot(authority, _attack(mode_variant="special"))
    structural_action = structural_state.action_affordances.actions[0]

    structural = evaluate_ordinary_attack(
        authority, structural_state, structural_action.action_id
    )

    assert structural.status is ResultStatus.INCOMPLETE_COVERAGE
    assert structural.problems[0].code is ErrorCode.MECHANICS_UNSUPPORTED

    concrete_state = _ordinary_attack_state(authority)
    effect = EffectState(
        "effect-test", KnownValue.exact("effect.test"), KnownValue.exact(True)
    )
    actors = tuple(
        replace(actor, effects=(effect,)) if actor.actor_id == "brother" else actor
        for actor in concrete_state.combatants
    )
    concrete_state = _with_actions(
        concrete_state,
        *concrete_state.action_affordances.actions,
        combatants=actors,
    )
    concrete = evaluate_ordinary_attack(
        authority,
        concrete_state,
        concrete_state.action_affordances.actions[0].action_id,
    )

    assert concrete.status is ResultStatus.INCOMPLETE_COVERAGE
    assert concrete.problems[0].code is ErrorCode.EVALUATION_UNSUPPORTED


def test_current_attack_and_contingent_aoo_share_effect_restrictions():
    authority = _authority()
    effect = EffectState(
        "effect-test", KnownValue.exact("effect.test"), KnownValue.exact(True)
    )

    attack_state = _ordinary_attack_state(authority)
    attack_actors = tuple(
        replace(actor, effects=(effect,)) if actor.actor_id == "brother" else actor
        for actor in attack_state.combatants
    )
    attack_state = _with_actions(
        attack_state,
        *attack_state.action_affordances.actions,
        combatants=attack_actors,
    )
    attack_result = evaluate_ordinary_attack(
        authority, attack_state, attack_state.action_affordances.actions[0].action_id
    )

    move = _move_action(reactions=(_reaction(),))
    move_state = _movement_state(authority, move)
    move_actors = tuple(
        replace(actor, effects=(effect,)) if actor.actor_id == "enemy" else actor
        for actor in move_state.combatants
    )
    move_state = _with_actions(
        move_state,
        *move_state.action_affordances.actions,
        combatants=move_actors,
    )
    move_result = evaluate_transition(
        authority, move_state, move_state.action_affordances.actions[0].action_id
    )

    assert attack_result.status is ResultStatus.INCOMPLETE_COVERAGE
    assert move_result.status is ResultStatus.INCOMPLETE_COVERAGE
    assert attack_result.problems[0].code is ErrorCode.EVALUATION_UNSUPPORTED
    assert move_result.problems[0].code is ErrorCode.EVALUATION_UNSUPPORTED
    assert attack_result.problems[0].message == move_result.problems[0].message


def test_contingent_aoo_uses_internal_attack_context_not_enemy_affordance(monkeypatch):
    authority = _authority()
    state = _movement_state(authority, _move_action(reactions=(_reaction(),)))
    seen = []
    original = transitions.evaluate_ordinary_attack

    def record_context(authority_arg, state_arg, context):
        seen.append(context)
        return original(authority_arg, state_arg, context)

    monkeypatch.setattr(transitions, "evaluate_ordinary_attack", record_context)

    result = evaluate_transition(
        authority, state, state.action_affordances.actions[0].action_id
    )

    assert result.status is ResultStatus.SUCCESS
    assert seen
    assert not isinstance(seen[0], ActionAffordance)
    assert seen[0].attacker_id == "enemy"
    assert seen[0].target_actor_id == "brother"


def test_unexpected_programmer_error_is_not_relabelled_as_coverage(monkeypatch):
    authority = _authority()
    state = _ordinary_attack_state(authority)

    def explode(*_args, **_kwargs):
        raise AttributeError("programmer bug")

    monkeypatch.setattr(outcomes, "_evaluate_ordinary_attack_context", explode)

    with pytest.raises(AttributeError, match="programmer bug"):
        evaluate_ordinary_attack(
            authority, state, state.action_affordances.actions[0].action_id
        )


def test_production_paths_enforce_resolution_stage_and_preserve_ledgers():
    authority = _authority()
    state = _ordinary_attack_state(authority)
    action = state.action_affordances.actions[0]

    good = evaluate_ordinary_attack(authority, state, action.action_id)
    assert good.status is ResultStatus.SUCCESS
    assert good.value is not None
    ledgers = dict(good.value.resolution_ledgers)
    assert set(ledgers) == {"ap_cost", "fatigue_cost", "displayed_hit_chance"}
    assert all(ledger.completed[-1].value == "OUTCOME" for ledger in ledgers.values())

    wrongly_staged = replace(
        action,
        ap_cost=replace(action.ap_cost, stage=ResolutionStage.STATIC_RULE),
    )
    bad_state = _with_actions(state, wrongly_staged)
    bad = evaluate_ordinary_attack(
        authority, bad_state, bad_state.action_affordances.actions[0].action_id
    )
    assert bad.status is ResultStatus.VALIDATION_FAILURE
    assert bad.problems[0].code is ErrorCode.VALIDATION_FAILED


def test_transition_preserves_reaction_and_reload_resolution_ledgers():
    authority = _authority()
    move_state = _movement_state(authority, _move_action(reactions=(_reaction(),)))

    move = evaluate_transition(
        authority, move_state, move_state.action_affordances.actions[0].action_id
    )

    assert move.status is ResultStatus.SUCCESS
    assert move.value is not None
    move_ledgers = dict(move.value.resolution_ledgers)
    assert set(move_ledgers) == {
        "ap_cost",
        "fatigue_cost",
        "aoo:east:enemy.displayed_hit_chance",
    }
    assert all(
        ledger.completed[-1].value == "OUTCOME" for ledger in move_ledgers.values()
    )

    reload_state = _snapshot(authority, _resource_action("actives.reload_bolt"))
    reload = evaluate_transition(
        authority,
        reload_state,
        reload_state.action_affordances.actions[0].action_id,
    )

    assert reload.status is ResultStatus.SUCCESS
    assert reload.value is not None
    assert set(dict(reload.value.resolution_ledgers)) == {
        "ap_cost",
        "fatigue_cost",
        "ammo_cost",
    }


def test_debug_oracle_resolved_input_cannot_enter_production_outcome_path():
    authority = _authority()
    state = _ordinary_attack_state(authority)
    action = state.action_affordances.actions[0]
    debug_preview = replace(
        action.preview,
        displayed_hit_chance=replace(
            action.preview.displayed_hit_chance,
            authority=ResolutionAuthority.DEBUG_ORACLE,
        ),
    )
    debug_action = replace(action, preview=debug_preview)
    debug_state = _with_actions(state, debug_action)

    result = evaluate_ordinary_attack(
        authority, debug_state, debug_state.action_affordances.actions[0].action_id
    )

    assert result.status is ResultStatus.VALIDATION_FAILURE
    assert result.problems[0].code is ErrorCode.VALIDATION_FAILED


def test_command_identity_ignores_provenance_and_reaction_consequences():
    fixture = _state(provenance=AffordanceProvenance.HANDCRAFTED_FIXTURE)
    game = _state(provenance=AffordanceProvenance.GAME_PLAYER_AFFORDANCE)
    assert (
        fixture.action_affordances.actions[0].action_id
        == game.action_affordances.actions[0].action_id
    )

    authority = _authority()
    first = _movement_state(
        authority, _move_action(reactions=(_reaction(hit_chance=67),))
    )
    second = _movement_state(
        authority, _move_action(reactions=(_reaction(hit_chance=55),))
    )
    assert (
        first.action_affordances.actions[0].action_id
        == second.action_affordances.actions[0].action_id
    )
    assert first.state_id != second.state_id


def test_reaction_authority_changes_state_identity_not_command_identity():
    authority = _authority()
    fixture_move = _move_action(reactions=(_reaction(),))
    fixture_state = _movement_state(authority, fixture_move)

    reaction = replace(
        fixture_move.contingent_reactions[0],
        hit_chance=replace(
            fixture_move.contingent_reactions[0].hit_chance,
            authority=ResolutionAuthority.GAME_PLAYER_AFFORDANCE,
        ),
    )
    game_move = replace(
        fixture_move,
        provenance=AffordanceProvenance.GAME_PLAYER_AFFORDANCE,
        ap_cost=replace(
            fixture_move.ap_cost,
            authority=ResolutionAuthority.GAME_PLAYER_AFFORDANCE,
        ),
        fatigue_cost=replace(
            fixture_move.fatigue_cost,
            authority=ResolutionAuthority.GAME_PLAYER_AFFORDANCE,
        ),
        charge_cost=replace(
            fixture_move.charge_cost,
            authority=ResolutionAuthority.GAME_PLAYER_AFFORDANCE,
        ),
        ammo_cost=replace(
            fixture_move.ammo_cost,
            authority=ResolutionAuthority.GAME_PLAYER_AFFORDANCE,
        ),
        item_action_cost=replace(
            fixture_move.item_action_cost,
            authority=ResolutionAuthority.GAME_PLAYER_AFFORDANCE,
        ),
        contingent_reactions=(reaction,),
    )
    game_state = _movement_state(authority, game_move)

    assert (
        fixture_state.action_affordances.actions[0].action_id
        == game_state.action_affordances.actions[0].action_id
    )
    assert fixture_state.state_id != game_state.state_id


def test_contingent_aoo_does_not_expand_with_future_ordinary_attack_catalog_entry():
    authority = _authority()
    chop = authority.catalog.entry("actives.chop")
    assert chop is not None
    future_skill = replace(chop, content_id="actives.future_attack")
    future_authority = MechanicsAuthority(
        replace(
            authority.catalog,
            entries=authority.catalog.entries + (future_skill,),
        ),
        authority.manifest,
    )
    reaction = replace(_reaction(), skill_id="actives.future_attack")
    state = _movement_state(
        future_authority,
        _move_action(reactions=(reaction,)),
    )

    result = evaluate_transition(
        future_authority,
        state,
        state.action_affordances.actions[0].action_id,
    )

    assert result.status is ResultStatus.INCOMPLETE_COVERAGE
    assert result.problems[0].code is ErrorCode.EVALUATION_UNSUPPORTED
    assert "damage profile is unsupported" in result.problems[0].message
