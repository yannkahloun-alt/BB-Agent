from dataclasses import fields, replace

import pytest

from bb_agent.evaluator import (
    DEFAULT_EVALUATION_PROFILE,
    EvaluationProfile,
    EvaluationWeights,
    UnitValuePolicy,
    evaluate_decision,
    score_candidate_features,
    select_candidate_evaluations,
)
from bb_agent.features import MetricRange, extract_candidate_features
from bb_agent.results import ResultStatus
from bb_agent.tactical_state import (
    HexCoord,
    InformationProfile,
    KnowledgeClass,
    KnownValue,
    Representation,
    TacticalState,
    Tile,
)
from test_mechanics import (
    _attack,
    _authority,
    _move_action,
    _movement_state,
    _ordinary_attack_state,
    _reaction,
    _snapshot,
    _wait,
)


def _base_features(action_id: str):
    authority = _authority()
    state = _snapshot(authority, _wait())
    source_id = state.action_affordances.actions[0].action_id
    result = extract_candidate_features(authority, state, source_id)
    assert result.status is ResultStatus.SUCCESS
    assert result.value is not None
    return replace(
        result.value,
        action_id=action_id,
        threat=replace(
            result.value.threat,
            hostile_zoc_pressure=MetricRange.exact(0),
        ),
    )


def _component(candidate, component_id: str):
    return next(
        component
        for component in candidate.components
        if component.component_id == component_id
    )


def _enemy(features, *, hp: float, armor: float = 0, kill: float = 0):
    return replace(
        features,
        enemy_effect=replace(
            features.enemy_effect,
            expected_hp_damage=MetricRange.exact(hp),
            expected_armor_damage=MetricRange.exact(armor),
            kill_probability=MetricRange.exact(kill),
        ),
    )


def _death_risk(features, probability: float, *, self_harm: float = 0):
    return replace(
        features,
        friendly_harm=replace(
            features.friendly_harm,
            expected_self_hp_damage=MetricRange.exact(self_harm),
            self_death_probability=MetricRange.exact(probability),
        ),
    )


def _scenario_flip_state(authority, *, omniscient_hp: int | None = None):
    state = _ordinary_attack_state(authority, hit_points=10)
    brother = next(actor for actor in state.combatants if actor.actor_id == "brother")
    enemy = next(actor for actor in state.combatants if actor.actor_id == "enemy")
    if omniscient_hp is None:
        enemy_hp = KnownValue(
            Representation.SET,
            KnowledgeClass.INFERRED,
            candidates=(5, 20),
            basis=("visible-wound-band",),
        )
        information_profile = InformationProfile.PLAYER_LEGAL
    else:
        enemy_hp = KnownValue.exact(
            omniscient_hp,
            KnowledgeClass.DEBUG_GROUND_TRUTH,
        )
        information_profile = InformationProfile.OMNISCIENT_DEBUG

    enemy_one = replace(
        enemy,
        resources=replace(enemy.resources, hit_points=enemy_hp),
    )
    enemy_two = replace(
        enemy,
        actor_id="enemy-2",
        position=KnownValue.exact("northeast"),
        resources=replace(
            enemy.resources,
            hit_points=KnownValue.exact(10),
        ),
    )

    attack_one = state.action_affordances.actions[0]
    preview = attack_one.preview
    if preview.affected_tile_ids is not None:
        preview = replace(
            preview,
            affected_tile_ids=replace(
                preview.affected_tile_ids,
                value=["northeast"],
            ),
        )
    attack_two = replace(
        attack_one,
        action_id="attack:enemy-2",
        target_actor_id="enemy-2",
        preview=preview,
    )

    origin = next(tile for tile in state.tiles if tile.tile_id == "origin")
    east = next(tile for tile in state.tiles if tile.tile_id == "east")
    origin = replace(
        origin,
        neighbors=("east", "northeast", None, None, None, None),
    )
    east = replace(
        east,
        neighbors=(None, None, "northeast", "origin", None, None),
    )
    northeast = Tile(
        "northeast",
        HexCoord(1, -1),
        0,
        KnownValue.exact("plain"),
        (None, None, None, None, "origin", "east"),
        "enemy-2",
    )

    values = {field.name: getattr(state, field.name) for field in fields(state)}
    values.update(
        state_id="",
        information_profile=information_profile,
        combatants=(brother, enemy_one, enemy_two),
        tiles=(origin, east, northeast),
        action_affordances=replace(
            state.action_affordances,
            actions=(attack_one, attack_two),
        ),
    )
    return TacticalState.create(**values)


def test_complete_decision_evaluation_is_exactly_deterministic():
    authority = _authority()
    state = _snapshot(authority, _wait())

    first = evaluate_decision(authority, state)
    second = evaluate_decision(authority, state)

    assert first.status is ResultStatus.SUCCESS
    assert first == second
    assert first.value is not None
    assert first.value.evaluator_version == "risk-evaluator.v1"
    assert first.value.evaluation_profile_fingerprint
    assert first.value.unit_value_policy_fingerprint
    assert first.value.ranking == (first.value.chosen_action_id,)


def test_incomplete_material_coverage_returns_no_ranking():
    authority = _authority()
    state = _snapshot(authority, _wait(), _attack("mod.unknown_aoe"))

    result = evaluate_decision(authority, state)

    assert result.status is ResultStatus.INCOMPLETE_COVERAGE
    assert result.value is None
    assert any(problem.mechanic_id == "mod.unknown_aoe" for problem in result.problems)


def test_high_mean_action_can_lose_to_materially_safer_candidate():
    risky_features = _death_risk(
        _enemy(_base_features("risky-attack"), hp=60, kill=0.9),
        0.4,
    )
    safe_features = _death_risk(
        _enemy(_base_features("safe-attack"), hp=35, kill=0.4),
        0,
    )
    risky = score_candidate_features(risky_features, "brother")
    safe = score_candidate_features(safe_features, "brother")

    selection = select_candidate_evaluations((risky, safe))

    assert risky.mean_tactical_value is not None
    assert safe.mean_tactical_value is not None
    assert risky.mean_tactical_value > safe.mean_tactical_value
    assert risky.tail_risk.selection_penalty > safe.tail_risk.selection_penalty
    assert selection.chosen_action_id == "safe-attack"


def test_zero_damage_protection_can_beat_low_value_attack_via_real_components():
    protective = _base_features("protective-move")
    protective = replace(
        protective,
        position=replace(
            protective.position,
            elevation_change=MetricRange.exact(2),
            elevation_advantage_contacts=MetricRange.exact(2),
        ),
        formation=replace(
            protective.formation,
            created_direct_screen_links=MetricRange.exact(2),
            lost_direct_screen_links=MetricRange.exact(0),
        ),
        control=replace(
            protective.control,
            flanked_hostiles=MetricRange.exact(2),
        ),
        mobility=replace(
            protective.mobility,
            open_adjacent_reposition_tiles=MetricRange.exact(6),
        ),
    )
    chip = _enemy(_base_features("chip-attack"), hp=10)
    protective_score = score_candidate_features(protective, "brother")
    chip_score = score_candidate_features(chip, "brother")

    selection = select_candidate_evaluations((protective_score, chip_score))

    assert protective.enemy_effect.expected_hp_damage.expected == 0
    assert (
        _component(
            protective_score,
            "position_control_ally_protection",
        ).selection_value
        > 0
    )
    assert selection.chosen_action_id == "protective-move"


def test_fatigue_and_future_capacity_change_resource_component_visibly():
    fresh = _base_features("fresh")
    locked = _base_features("locked")
    fresh = replace(
        fresh,
        resources=replace(
            fresh.resources,
            remaining_action_points=MetricRange.exact(5),
            fatigue_headroom=MetricRange.exact(50),
        ),
        future_capacity=replace(
            fresh.future_capacity,
            current_cost_template_count=2,
            ap_fat_feasible_template_count=MetricRange.exact(2),
            ap_fat_locked_template_count=MetricRange.exact(0),
        ),
    )
    locked = replace(
        locked,
        resources=replace(
            locked.resources,
            remaining_action_points=MetricRange.exact(0),
            fatigue_headroom=MetricRange.exact(2),
        ),
        future_capacity=replace(
            locked.future_capacity,
            current_cost_template_count=2,
            ap_fat_feasible_template_count=MetricRange.exact(0),
            ap_fat_locked_template_count=MetricRange.exact(2),
        ),
    )
    fresh_score = score_candidate_features(fresh, "brother")
    locked_score = score_candidate_features(locked, "brother")

    fresh_resource = _component(fresh_score, "resource_fat_future_capacity")
    locked_resource = _component(locked_score, "resource_fat_future_capacity")

    assert fresh_resource.selection_value > locked_resource.selection_value
    assert fresh_score.ranking_value > locked_score.ranking_value


def test_injected_unit_value_policy_changes_loss_cost_without_state_mutation():
    features = _death_risk(
        _base_features("vulnerable-action"),
        0.2,
        self_harm=20,
    )
    default = score_candidate_features(features, "brother")
    strategic_policy = UnitValuePolicy(
        version="strategic-test.v1",
        actor_values=(("brother", 3.0),),
    )
    strategic = score_candidate_features(
        features,
        "brother",
        unit_value_policy=strategic_policy,
    )

    assert strategic.features is features
    assert strategic.tail_risk.unit_value == 3
    assert strategic.tail_risk.selection_penalty > default.tail_risk.selection_penalty
    assert (
        _component(strategic, "immediate_friendly_harm").selection_value
        < _component(default, "immediate_friendly_harm").selection_value
    )
    assert strategic.ranking_value < default.ranking_value


def test_omniscient_aleatory_aoo_spread_is_not_epistemic_uncertainty():
    authority = _authority()
    move = _move_action(reactions=(_reaction(),))
    state = _movement_state(authority, move)

    result = evaluate_decision(authority, state)

    assert result.status is ResultStatus.SUCCESS
    assert result.value is not None
    candidate = result.value.candidates[0]
    damage = candidate.features.friendly_harm.expected_self_hp_damage
    assert damage.maximum > damage.minimum
    assert damage.expected is not None
    assert candidate.uncertainty_span == pytest.approx(0)
    assert candidate.information_sensitive is False
    assert result.value.information_sensitive is False
    facts = {
        fact.component_id: fact.contribution for fact in candidate.explanation_facts
    }
    assert facts["uncertainty_robustness_adjustment"] == pytest.approx(0)


def test_player_legal_rank_flip_uses_coherent_hidden_state_scenarios():
    authority = _authority()
    weights = EvaluationWeights(
        enemy_effect=1,
        immediate_friendly_harm=0,
        post_action_exposure=0,
        position_control_protection=0,
        resource_future_capacity=0,
        tempo=0,
    )
    profile = EvaluationProfile(
        weights=weights,
        tail_risk_weight=0,
        uncertainty_weight=0,
        near_tie_margin=0.001,
    )
    player_legal = _scenario_flip_state(authority)

    result = evaluate_decision(authority, player_legal, profile)

    assert result.status is ResultStatus.SUCCESS
    assert result.value is not None
    assert result.value.information_sensitive is True
    assert len(result.value.epistemic_scenarios) == 2
    assert (
        len(
            {scenario.chosen_action_id for scenario in result.value.epistemic_scenarios}
        )
        == 2
    )
    assert {
        assignment.value
        for scenario in result.value.epistemic_scenarios
        for assignment in scenario.assignments
        if assignment.actor_id == "enemy" and assignment.field == "resources.hit_points"
    } == {5, 20}

    for hp in (5, 20):
        omniscient = evaluate_decision(
            authority,
            _scenario_flip_state(authority, omniscient_hp=hp),
            profile,
        )
        assert omniscient.status is ResultStatus.SUCCESS
        assert omniscient.value is not None
        assert omniscient.value.information_sensitive is False
        assert omniscient.value.epistemic_scenarios == ()


def test_near_tie_uses_frozen_resource_then_action_id_tie_path():
    free = _base_features("b-free")
    costly = _base_features("a-costly")
    costly = replace(
        costly,
        resources=replace(costly.resources, ammo_consumed=1),
    )
    weights = replace(
        DEFAULT_EVALUATION_PROFILE.weights,
        resource_future_capacity=0,
    )
    profile = EvaluationProfile(
        weights=weights,
        near_tie_margin=0.2,
    )
    free_score = score_candidate_features(free, "brother", profile)
    costly_score = score_candidate_features(costly, "brother", profile)

    selection = select_candidate_evaluations((costly_score, free_score), profile)

    assert free_score.ranking_value == pytest.approx(costly_score.ranking_value)
    assert selection.chosen_action_id == "b-free"
    assert selection.near_tie_groups == (("b-free", "a-costly"),)
    assert selection.tie_breaks[0].criteria == (
        "lower_tail_risk",
        "lower_epistemic_uncertainty",
        "lower_irreversible_resource_cost",
        "stable_action_id",
    )


def test_strict_dominance_is_reported_without_opaque_pruning():
    strong = score_candidate_features(
        _enemy(_base_features("strong"), hp=60, kill=1),
        "brother",
    )
    weak = score_candidate_features(
        _enemy(_base_features("weak"), hp=5),
        "brother",
    )

    selection = select_candidate_evaluations((weak, strong))
    weak_after = next(
        candidate for candidate in selection.candidates if candidate.action_id == "weak"
    )

    assert weak_after.dominated_by == "strong"
    assert selection.chosen_action_id == "strong"
    assert "weak" in selection.ranking


def test_declared_death_guardrail_can_exclude_higher_primary_score():
    risky = _death_risk(
        _enemy(_base_features("risky"), hp=60, kill=1),
        0.2,
    )
    safe = _enemy(_base_features("safe"), hp=5)
    profile = EvaluationProfile(
        tail_risk_weight=0,
        max_self_death_probability=0.1,
    )
    risky_score = score_candidate_features(risky, "brother", profile)
    safe_score = score_candidate_features(safe, "brother", profile)

    assert risky_score.ranking_value > safe_score.ranking_value
    selection = select_candidate_evaluations((risky_score, safe_score), profile)

    assert risky_score.guardrail_findings == ("MAX_SELF_DEATH_PROBABILITY",)
    assert selection.chosen_action_id == "safe"


def test_explanation_facts_reconcile_and_preserve_required_component_ids():
    features = _death_risk(
        _enemy(_base_features("explain"), hp=35, armor=20, kill=0.25),
        0.05,
        self_harm=5,
    )
    score = score_candidate_features(features, "brother")

    facts = {fact.component_id: fact.contribution for fact in score.explanation_facts}

    assert set(facts) == {
        "enemy_effect",
        "immediate_friendly_harm",
        "post_action_exposure",
        "position_control_ally_protection",
        "resource_fat_future_capacity",
        "tempo_turn_order",
        "tail_risk_penalty",
        "uncertainty_robustness_adjustment",
    }
    assert sum(facts.values()) == pytest.approx(score.ranking_value)
