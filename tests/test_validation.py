from dataclasses import replace

from bb_agent.evaluator import EvaluationProfile, EvaluationWeights
from bb_agent.fixtures import (
    FixtureEnvelope,
    FixtureMetadata,
    FixtureSeverity,
    FixtureSourceKind,
    ReviewStatus,
)
from bb_agent.tactical_state import ActionKind
from bb_agent.trace import run_decision_trace
from bb_agent.validation import (
    EXPECTATION_VERSION,
    AssertionStatus,
    FixtureExpectations,
    RegressionKind,
    classify_trace_change,
    run_fixture_validation,
    run_validation_corpus,
)
from test_evaluator import _scenario_flip_state
from test_mechanics import _attack, _authority, _ordinary_attack_state, _snapshot, _wait


def _fixture(
    state,
    expectations,
    *,
    fixture_id="validation-fixture",
    severity=FixtureSeverity.CORE,
    taxonomy=("trace_failure_coverage",),
    review_status=ReviewStatus.PROMOTED,
    oracle_annotations=None,
):
    metadata = FixtureMetadata(
        fixture_id=fixture_id,
        source_kind=FixtureSourceKind.HANDCRAFTED,
        taxonomy=taxonomy,
        severity=severity,
        scenario_intent="exercise generic validation expectations",
        ruleset_content_fingerprint=state.ruleset.content_fingerprint,
        information_profile=state.information_profile,
        affordance_completeness=state.action_affordances.completeness,
        expectation_version=(EXPECTATION_VERSION if expectations is not None else None),
        review_status=review_status,
    )
    return FixtureEnvelope.create(
        metadata=metadata,
        state=state,
        expectations=expectations,
        oracle_annotations=oracle_annotations,
    )


def _evaluation_record(trace, action_id):
    return next(
        record for record in trace.evaluations if record["action_id"] == action_id
    )


def _enemy_effect_only_profile(*, version="m1-evaluation-profile.v1"):
    return EvaluationProfile(
        version=version,
        weights=EvaluationWeights(
            enemy_effect=1,
            immediate_friendly_harm=0,
            post_action_exposure=0,
            position_control_protection=0,
            resource_future_capacity=0,
            tempo=0,
        ),
        tail_risk_weight=0,
        uncertainty_weight=0,
        near_tie_margin=0.001,
    )


def test_promoted_fixture_supports_full_generic_expectation_vocabulary():
    authority = _authority()
    state = _snapshot(authority, _wait(), _wait(ActionKind.END_TURN))
    profile = replace(EvaluationProfile(), near_tie_margin=1000)
    baseline = run_decision_trace(authority, state, profile)
    assert baseline.selection is not None
    ranking = tuple(baseline.selection["ranking"])
    assert len(ranking) == 2
    chosen = ranking[0]
    chosen_record = _evaluation_record(baseline, chosen)
    ranking_value = chosen_record["evaluation"]["ranking_value"]
    action_ids = [action.action_id for action in state.action_affordances.actions]

    expectations = {
        "version": EXPECTATION_VERSION,
        "expected_status": "SUCCESS",
        "acceptable_top1": [chosen],
        "forbidden_top1": ["action:catastrophic-placeholder"],
        "required_orderings": [[ranking[0], ranking[1]]],
        "top_k": [{"any_of": [ranking[1]], "k": 2}],
        "near_ties": [{"action_ids": list(ranking), "expected": True}],
        "numeric_relations": [
            {
                "left": {
                    "action_id": "$chosen",
                    "path": "evaluation.ranking_value",
                },
                "op": "==",
                "right_value": ranking_value,
            }
        ],
        "required_explanations": [
            {
                "action_id": "$chosen",
                "component_ids": [
                    "enemy_effect",
                    "tail_risk_penalty",
                    "uncertainty_robustness_adjustment",
                ],
            }
        ],
        "exact_legal_action_ids": action_ids,
        "action_facts": [{"action_id": chosen, "path": "ap_cost.value", "equals": 0}],
        "expected_output_fingerprint": baseline.output_fingerprint,
    }
    report = run_fixture_validation(
        authority,
        _fixture(state, expectations),
        profile,
    )

    assert report.passed is True, report.blocking_failures
    assert report.blocking_failures == ()
    assert report.review_findings == ()
    assert {item.assertion_id for item in report.assertions} >= {
        "state_identity",
        "affordance_integrity",
        "exact_replay",
        "acceptable_top1",
        "forbidden_top1",
        "ordering:" + ranking[0] + ">" + ranking[1],
        "top_k:0",
        "near_tie:0",
        "numeric_relation:0",
        "explanation_components:0",
        "output_fingerprint",
    }


def test_calibration_disagreement_is_review_only_not_a_gated_failure():
    authority = _authority()
    state = _snapshot(authority, _wait())
    fixture = _fixture(
        state,
        {
            "version": EXPECTATION_VERSION,
            "acceptable_top1": ["action:not-the-winner"],
        },
        severity=FixtureSeverity.CALIBRATION,
        review_status=ReviewStatus.REVIEWED,
    )

    report = run_fixture_validation(authority, fixture)

    assert report.passed is True, report.blocking_failures
    finding = next(
        item for item in report.assertions if item.assertion_id == "acceptable_top1"
    )
    assert finding.status is AssertionStatus.REVIEW
    assert finding.gated is False


def test_expected_incomplete_coverage_passes_but_ranking_fixture_fails_closed():
    authority = _authority()
    state = _snapshot(authority, _wait(), _attack("mod.unknown_aoe"))
    coverage_fixture = _fixture(
        state,
        {
            "version": EXPECTATION_VERSION,
            "expected_status": "INCOMPLETE_COVERAGE",
            "expected_mechanic_ids": ["mod.unknown_aoe"],
        },
    )
    ranking_fixture = _fixture(
        state,
        {
            "version": EXPECTATION_VERSION,
            "acceptable_top1": [state.action_affordances.actions[0].action_id],
        },
        fixture_id="ranking-requires-coverage",
    )

    coverage_report = run_fixture_validation(authority, coverage_fixture)
    ranking_report = run_fixture_validation(authority, ranking_fixture)

    assert coverage_report.passed is True
    assert coverage_report.trace is not None
    assert coverage_report.trace.selection is None
    assert ranking_report.passed is False
    assert any(
        item.assertion_id == "ranking_available" and item.status is AssertionStatus.FAIL
        for item in ranking_report.assertions
    )


def test_oracle_affordance_completeness_metadata_is_checked_generically():
    authority = _authority()
    state = _snapshot(authority, _wait())
    action_ids = [action.action_id for action in state.action_affordances.actions]
    fixture = _fixture(
        state,
        {
            "version": EXPECTATION_VERSION,
            "expected_status": "SUCCESS",
            "assert_oracle_affordance_set": True,
        },
        oracle_annotations={
            "affordance_set_complete": True,
            "legal_action_ids": action_ids,
        },
    )

    report = run_fixture_validation(authority, fixture)

    assert report.passed is True, report.blocking_failures
    assert next(
        item
        for item in report.assertions
        if item.assertion_id == "oracle_affordance_exact"
    ).passed


def test_information_sensitive_expectation_uses_recorded_scenario_ranking():
    authority = _authority()
    state = _scenario_flip_state(authority)
    profile = _enemy_effect_only_profile()
    baseline = run_decision_trace(authority, state, profile)
    assert baseline.selection is not None
    assert baseline.selection["information_sensitive"] is True
    fixture = _fixture(
        state,
        {
            "version": EXPECTATION_VERSION,
            "acceptable_top1": [baseline.selection["chosen_action_id"]],
            "information_sensitive": True,
            "required_explanations": [
                {"action_id": "$chosen", "component_ids": ["enemy_effect"]}
            ],
        },
        taxonomy=("uncertainty_no_cheat",),
    )

    report = run_fixture_validation(authority, fixture, profile)

    assert report.passed is True, report.blocking_failures
    assert next(
        item
        for item in report.assertions
        if item.assertion_id == "information_sensitive"
    ).passed


def test_regression_classification_distinguishes_frozen_categories():
    authority = _authority()
    state = _ordinary_attack_state(authority)
    before = run_decision_trace(authority, state)
    assert before.selection is not None
    winner = before.selection["chosen_action_id"]
    version_fixture = _fixture(
        state,
        {
            "version": EXPECTATION_VERSION,
            "acceptable_top1": [winner],
            "allow_model_version_change": True,
        },
    )
    after_version = run_decision_trace(
        authority,
        state,
        replace(EvaluationProfile(), version="m1-evaluation-profile.test-v2"),
    )
    intended = classify_trace_change(version_fixture, before, after_version)
    assert intended.kind is RegressionKind.INTENDED_MODEL_VERSION_CHANGE

    profile = _enemy_effect_only_profile()
    low = _scenario_flip_state(authority, omniscient_hp=5)
    high = _scenario_flip_state(authority, omniscient_hp=20)
    low_trace = run_decision_trace(authority, low, profile)
    high_trace = run_decision_trace(authority, high, profile)
    assert low_trace.selection is not None
    assert high_trace.selection is not None
    assert (
        low_trace.selection["chosen_action_id"]
        != high_trace.selection["chosen_action_id"]
    )
    acceptable = [
        low_trace.selection["chosen_action_id"],
        high_trace.selection["chosen_action_id"],
    ]
    substitution_fixture = _fixture(
        low,
        {"version": EXPECTATION_VERSION, "acceptable_top1": acceptable},
    )
    substitution = classify_trace_change(
        substitution_fixture,
        low_trace,
        high_trace,
    )
    assert substitution.kind is RegressionKind.ACCEPTABLE_SET_SUBSTITUTION

    hard_fixture = _fixture(
        low,
        {
            "version": EXPECTATION_VERSION,
            "acceptable_top1": [low_trace.selection["chosen_action_id"]],
        },
        fixture_id="hard-regression",
    )
    hard = classify_trace_change(hard_fixture, low_trace, high_trace)
    assert hard.kind is RegressionKind.HARD_GATED_FAILURE

    calibration_fixture = _fixture(
        low,
        None,
        fixture_id="calibration-change",
        severity=FixtureSeverity.CALIBRATION,
        review_status=ReviewStatus.DRAFT,
    )
    calibration = classify_trace_change(
        calibration_fixture,
        low_trace,
        high_trace,
    )
    assert calibration.kind is RegressionKind.CALIBRATION_REVIEW_REQUIRED


def test_corpus_summary_reports_taxonomy_severity_and_nonblocking_reviews():
    authority = _authority()
    state = _snapshot(authority, _wait())
    baseline = run_decision_trace(authority, state)
    assert baseline.selection is not None
    chosen = baseline.selection["chosen_action_id"]
    safety = _fixture(
        state,
        {"version": EXPECTATION_VERSION, "acceptable_top1": [chosen]},
        fixture_id="safety",
        severity=FixtureSeverity.SAFETY_CRITICAL,
        taxonomy=("survival_catastrophic_risk", "trace_failure_coverage"),
    )
    calibration = _fixture(
        state,
        {
            "version": EXPECTATION_VERSION,
            "acceptable_top1": ["action:review-me"],
        },
        fixture_id="calibration",
        severity=FixtureSeverity.CALIBRATION,
        taxonomy=("tempo_wait_end_turn",),
        review_status=ReviewStatus.REVIEWED,
    )

    report = run_validation_corpus(authority, (safety, calibration))

    assert report.passed is True, report.blocking_failures
    assert report.coverage.total_fixtures == 2
    assert report.coverage.gated_fixtures == 1
    assert report.coverage.calibration_fixtures == 1
    assert report.coverage.safety_critical_fixtures == 1
    assert dict(report.coverage.taxonomy_counts) == {
        "survival_catastrophic_risk": 1,
        "tempo_wait_end_turn": 1,
        "trace_failure_coverage": 1,
    }
    assert report.coverage.blocking_failure_count == 0
    assert report.coverage.review_finding_count >= 1
    assert report.coverage.median_decision_ns is not None
    assert report.coverage.p95_decision_ns is not None
    assert report.coverage.max_decision_ns is not None


def test_expectation_schema_rejects_ranking_assertion_on_expected_failure():
    try:
        FixtureExpectations.from_json(
            {
                "version": EXPECTATION_VERSION,
                "expected_status": "INCOMPLETE_COVERAGE",
                "acceptable_top1": ["action:any"],
            }
        )
    except ValueError as exc:
        assert "ranking assertions" in str(exc)
    else:
        raise AssertionError("invalid expectation combination should fail")


def test_calibration_still_hard_fails_status_and_missing_ranking_coverage():
    authority = _authority()
    state = _snapshot(authority, _wait(), _attack("mod.unknown_aoe"))
    status_fixture = _fixture(
        state,
        {"version": EXPECTATION_VERSION, "expected_status": "SUCCESS"},
        fixture_id="calibration-status",
        severity=FixtureSeverity.CALIBRATION,
        review_status=ReviewStatus.REVIEWED,
    )
    ranking_fixture = _fixture(
        state,
        {
            "version": EXPECTATION_VERSION,
            "acceptable_top1": [state.action_affordances.actions[0].action_id],
        },
        fixture_id="calibration-ranking-coverage",
        severity=FixtureSeverity.CALIBRATION,
        review_status=ReviewStatus.REVIEWED,
    )

    status_report = run_fixture_validation(authority, status_fixture)
    ranking_report = run_fixture_validation(authority, ranking_fixture)

    assert status_report.passed is False
    status_assertion = next(
        item
        for item in status_report.assertions
        if item.assertion_id == "expected_status"
    )
    assert status_assertion.status is AssertionStatus.FAIL
    assert status_assertion.gated is True

    assert ranking_report.passed is False
    ranking_assertion = next(
        item
        for item in ranking_report.assertions
        if item.assertion_id == "ranking_available"
    )
    assert ranking_assertion.status is AssertionStatus.FAIL
    assert ranking_assertion.gated is True
