from dataclasses import fields, replace

import pytest

import bb_agent.evaluator as evaluator_module
from bb_agent.evaluator import (
    DEFAULT_EVALUATION_PROFILE,
    EvaluationProfile,
    evaluate_decision,
)
from bb_agent.results import ResultStatus
from bb_agent.tactical_state import ActionKind, TacticalState
from bb_agent.trace import (
    DecisionTrace,
    compare_traces,
    replay_decision_trace,
    run_decision_trace,
)
from test_evaluator import _scenario_flip_state
from test_mechanics import _attack, _authority, _ordinary_attack_state, _snapshot, _wait


def _with_raw_capture(state: TacticalState, raw_capture_id: str) -> TacticalState:
    values = {field.name: getattr(state, field.name) for field in fields(state)}
    values.update(state_id="", raw_capture_id=raw_capture_id)
    return TacticalState.create(**values)


def test_repeated_trace_has_exact_semantic_identity_despite_measured_timings():
    authority = _authority()
    state = _ordinary_attack_state(authority)

    first = run_decision_trace(authority, state, implementation_revision="test-rev")
    second = run_decision_trace(authority, state, implementation_revision="test-rev")

    assert first.output_fingerprint == second.output_fingerprint
    assert first.trace_id == second.trace_id
    assert first.selection is not None
    assert second.selection is not None
    assert first.selection["ranking"] == second.selection["ranking"]
    assert first.selection["chosen_action_id"] == second.selection["chosen_action_id"]
    assert first.performance["stage_timings_ns"] != {}
    assert second.performance["stage_timings_ns"] != {}

    changed_performance = replace(
        first,
        performance={
            "stage_timings_ns": {"validation": 999_999_999},
            "counters": first.performance["counters"],
        },
    )
    assert changed_performance.output_fingerprint == first.output_fingerprint
    assert changed_performance.trace_id == first.trace_id


def test_trace_roundtrip_and_replay_regenerate_exact_output():
    authority = _authority()
    state = _ordinary_attack_state(authority)
    trace = run_decision_trace(authority, state)

    decoded = DecisionTrace.from_json_bytes(trace.to_json_bytes())
    replay = replay_decision_trace(authority, decoded)

    assert decoded == trace
    assert replay.matches is True
    assert replay.ranking_matches is True
    assert replay.chosen_action_matches is True
    assert replay.actual_trace.output_fingerprint == trace.output_fingerprint


def test_trace_candidate_records_expose_action_outcome_scoring_risk_and_explanations():
    authority = _authority()
    state = _ordinary_attack_state(authority)

    trace = run_decision_trace(authority, state)

    assert trace.failure is None
    assert trace.selection is not None
    assert len(trace.evaluations) == 1
    record = trace.evaluations[0]
    assert record["action_id"] == trace.selection["chosen_action_id"]
    assert record["coverage_status"] == "SUPPORTED"
    assert record["action"] is not None
    costs = record["deterministic_costs"]
    assert costs["ap_cost"] is not None
    assert costs["fatigue_cost"] is not None

    outcome = record["outcome"]
    assert outcome["method"] == "exact_branch_enumeration"
    assert outcome["branch_count"] > 0
    assert outcome["sample_count"] == 0
    assert outcome["simulator_seed"] is None

    evaluation = record["evaluation"]
    assert evaluation["features"]["enemy_effect"]
    assert evaluation["components"]
    assert evaluation["tail_risk"]
    assert evaluation["ranking_value"] is not None
    contributions = [fact["contribution"] for fact in evaluation["explanation_facts"]]
    assert sum(contributions) == pytest.approx(evaluation["ranking_value"])


def test_trace_performance_diagnostics_do_not_change_decision_result():
    authority = _authority()
    state = _ordinary_attack_state(authority)

    direct_result = evaluate_decision(authority, state)
    direct = run_decision_trace(authority, state)
    assert direct_result.status is ResultStatus.SUCCESS
    assert direct_result.value is not None
    assert direct.selection is not None
    assert tuple(direct.selection["ranking"]) == direct_result.value.ranking
    assert direct.selection["chosen_action_id"] == direct_result.value.chosen_action_id
    timings = direct.performance["stage_timings_ns"]
    counters = direct.performance["counters"]

    assert set(timings) == {
        "coverage",
        "outcome_and_features",
        "scoring",
        "selection",
        "validation",
    }
    assert all(value >= 0 for value in timings.values())
    assert counters["legal_candidate_count"] == 1
    assert counters["evaluated_candidate_count"] == 1
    assert counters["outcome_branch_count"] > 0
    assert counters["sample_count"] == 0
    assert direct.selection is not None


def test_incomplete_coverage_emits_structured_failure_trace_without_ranking():
    authority = _authority()
    state = _snapshot(authority, _wait(), _attack("mod.unknown_aoe"))

    trace = run_decision_trace(authority, state)

    assert trace.selection is None
    assert trace.evaluations == ()
    assert trace.failure is not None
    assert trace.failure["status"] == ResultStatus.INCOMPLETE_COVERAGE.value
    assert trace.generation["decision_status"] == ResultStatus.INCOMPLETE_COVERAGE.value
    diagnostics = trace.generation["coverage_diagnostics"]
    assert any(item["mechanic_id"] == "mod.unknown_aoe" for item in diagnostics)
    assert DecisionTrace.from_json_bytes(trace.to_json_bytes()) == trace
    replay = replay_decision_trace(authority, trace)
    assert replay.matches is True


def test_invalid_state_emits_validation_failure_trace():
    authority = _authority()
    state = replace(_ordinary_attack_state(authority), state_id="stale-state-id")

    trace = run_decision_trace(authority, state)

    assert trace.selection is None
    assert trace.failure is not None
    assert trace.failure["stage"] == "validation"
    assert trace.failure["status"] == ResultStatus.VALIDATION_FAILURE.value
    assert trace.generation["decision_status"] == ResultStatus.VALIDATION_FAILURE.value


def test_player_legal_and_debug_traces_identify_profile_and_shared_raw_capture():
    authority = _authority()
    player = _with_raw_capture(_scenario_flip_state(authority), "capture-22")
    debug = _with_raw_capture(
        _scenario_flip_state(authority, omniscient_hp=5),
        "capture-22",
    )

    player_trace = run_decision_trace(authority, player)
    debug_trace = run_decision_trace(authority, debug)

    assert player_trace.input["raw_capture_id"] == "capture-22"
    assert debug_trace.input["raw_capture_id"] == "capture-22"
    assert player_trace.input["information_profile"] == "player_legal"
    assert debug_trace.input["information_profile"] == "omniscient_debug"
    assert player_trace.input["state_id"] != debug_trace.input["state_id"]
    assert player_trace.output_fingerprint != debug_trace.output_fingerprint


def test_trace_diff_reports_component_and_rank_deltas():
    authority = _authority()
    before_state = _scenario_flip_state(authority, omniscient_hp=5)
    after_state = _scenario_flip_state(authority, omniscient_hp=20)
    profile = EvaluationProfile(
        weights=replace(
            DEFAULT_EVALUATION_PROFILE.weights,
            enemy_effect=1.0,
            post_action_exposure=0.0,
            position_control_protection=0.0,
            resource_future_capacity=0.0,
            tempo=0.0,
        ),
        tail_risk_weight=0.0,
        uncertainty_weight=0.0,
        near_tie_margin=0.001,
    )

    before = run_decision_trace(authority, before_state, profile)
    after = run_decision_trace(authority, after_state, profile)
    diff = compare_traces(before, after)

    assert diff.output_fingerprint_changed is True
    assert diff.chosen_action_changed is True
    assert diff.rank_deltas
    assert diff.component_deltas
    assert any(delta.component_id == "enemy_effect" for delta in diff.component_deltas)


def test_raw_capture_linkage_does_not_change_semantic_output_identity():
    authority = _authority()
    base = _ordinary_attack_state(authority)
    first = run_decision_trace(authority, _with_raw_capture(base, "capture-a"))
    second = run_decision_trace(authority, _with_raw_capture(base, "capture-b"))

    assert first.input["state_id"] == second.input["state_id"]
    assert first.input["raw_capture_id"] == "capture-a"
    assert second.input["raw_capture_id"] == "capture-b"
    assert first.output_fingerprint == second.output_fingerprint
    assert first.trace_id == second.trace_id


def test_trace_diff_uses_authoritative_legal_candidates_across_coverage_failure():
    authority = _authority()
    before = run_decision_trace(authority, _snapshot(authority, _wait()))
    after = run_decision_trace(
        authority,
        _snapshot(authority, _wait(), _attack("mod.unknown_aoe")),
    )

    before_ids = {
        action["action_id"] for action in before.generation["legal_candidates"]
    }
    after_ids = {action["action_id"] for action in after.generation["legal_candidates"]}
    assert after.failure is not None
    assert after.failure["status"] == ResultStatus.INCOMPLETE_COVERAGE.value
    assert after.evaluations == ()

    diff = compare_traces(before, after)

    assert diff.added_action_ids == tuple(sorted(after_ids - before_ids))
    assert diff.removed_action_ids == tuple(sorted(before_ids - after_ids))
    assert diff.added_action_ids


def test_unexpected_second_candidate_outcome_exception_keeps_current_stage(monkeypatch):
    authority = _authority()
    state = _snapshot(authority, _wait(), _wait(ActionKind.END_TURN))
    original = evaluator_module.extract_candidate_features
    calls = 0

    def explode_on_second_candidate(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("second candidate outcome failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(
        evaluator_module,
        "extract_candidate_features",
        explode_on_second_candidate,
    )

    trace = run_decision_trace(authority, state)

    assert trace.failure is not None
    assert trace.failure["status"] == "EVALUATION_EXCEPTION"
    assert trace.failure["stage"] == "outcome_and_features"
