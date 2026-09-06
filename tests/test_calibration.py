from dataclasses import replace
from pathlib import Path

from bb_agent.evaluator import (
    DEFAULT_EVALUATION_PROFILE,
    DEFAULT_UNIT_VALUE_POLICY,
    score_candidate_features,
)
from bb_agent.features import MetricRange
from bb_agent.fixtures import FixtureEnvelope, load_fixture
from bb_agent.results import ResultStatus
from bb_agent.validation import run_validation_corpus
from bb_agent.versions import CURRENT_VERSIONS
from test_evaluator import _base_features
from test_mechanics import _authority

ROOT = Path(__file__).parent
FIXTURE_DIRS = (
    ROOT / "fixtures" / "ticket_24",
    ROOT / "fixtures" / "ticket_25",
)
FINAL_PROFILE_FINGERPRINT = (
    "2e0ff58c4c57a80dc37eb86da5d49ef573057abd73eb158801f5c600c0c6ffcb"
)
DEFAULT_UNIT_VALUE_FINGERPRINT = (
    "170f540b3f76cb01ca88048dcb13cb66f57f96b2ea464c6a122292309179c2b7"
)


def _load_corpus() -> tuple[FixtureEnvelope, ...]:
    fixtures = []
    for directory in FIXTURE_DIRS:
        for path in sorted(directory.glob("*.json")):
            loaded = load_fixture(path)
            assert loaded.status is ResultStatus.SUCCESS, loaded.problems
            assert loaded.value is not None
            fixtures.append(loaded.value)
    return tuple(fixtures)


def _component(candidate, component_id: str):
    return next(
        component
        for component in candidate.components
        if component.component_id == component_id
    )


def _semantic_result(report):
    trace = report.trace
    assert trace is not None
    if trace.selection is None:
        return (
            report.fixture_id,
            trace.output_fingerprint,
            trace.generation["decision_status"],
            None,
            (),
        )
    return (
        report.fixture_id,
        trace.output_fingerprint,
        trace.generation["decision_status"],
        trace.selection["chosen_action_id"],
        tuple(trace.selection["ranking"]),
    )


def test_final_calibrated_profile_identity_is_pinned() -> None:
    profile = DEFAULT_EVALUATION_PROFILE

    assert profile.version == "m1-evaluation-profile.v2"
    assert CURRENT_VERSIONS.evaluation_config == profile.version
    assert profile.fingerprint == FINAL_PROFILE_FINGERPRINT
    assert profile.weights.enemy_effect == 1.25
    assert profile.weights.immediate_friendly_harm == 1.25
    assert profile.weights.post_action_exposure == 0.8
    assert profile.weights.position_control_protection == 0.8
    assert profile.weights.resource_future_capacity == 0.65
    assert profile.weights.tempo == 0.35
    assert profile.tail_risk_weight == 2.5
    assert profile.uncertainty_weight == 0.25
    assert profile.near_tie_margin == 0.05
    assert profile.max_self_death_probability is None

    assert DEFAULT_UNIT_VALUE_POLICY.version == "m1-common-preservation.v1"
    assert DEFAULT_UNIT_VALUE_POLICY.fingerprint == DEFAULT_UNIT_VALUE_FINGERPRINT


def test_locked_template_count_is_diagnostic_not_a_second_scoring_term() -> None:
    features = _base_features("resource-dedup")
    one_locked = replace(
        features,
        future_capacity=replace(
            features.future_capacity,
            current_cost_template_count=2,
            ap_fat_feasible_template_count=MetricRange.exact(1),
            ap_fat_locked_template_count=MetricRange.exact(1),
        ),
    )
    two_locked = replace(
        one_locked,
        future_capacity=replace(
            one_locked.future_capacity,
            ap_fat_locked_template_count=MetricRange.exact(2),
        ),
    )

    first = score_candidate_features(one_locked, "brother")
    second = score_candidate_features(two_locked, "brother")

    assert (
        first.features.future_capacity.ap_fat_locked_template_count
        != second.features.future_capacity.ap_fat_locked_template_count
    )
    assert _component(first, "resource_fat_future_capacity") == _component(
        second,
        "resource_fat_future_capacity",
    )
    assert first.ranking_value == second.ranking_value


def test_full_gated_corpus_is_repeatably_deterministic_under_final_profile() -> None:
    fixtures = _load_corpus()
    assert len(fixtures) == 54

    first = run_validation_corpus(_authority(), fixtures)
    second = run_validation_corpus(_authority(), fixtures)

    assert first.passed, [
        (report.fixture_id, report.blocking_failures)
        for report in first.fixtures
        if report.blocking_failures
    ]
    assert second.passed, [
        (report.fixture_id, report.blocking_failures)
        for report in second.fixtures
        if report.blocking_failures
    ]
    assert first.coverage.safety_critical_fixtures == 10
    assert first.coverage.blocking_failure_count == 0
    assert tuple(_semantic_result(report) for report in first.fixtures) == tuple(
        _semantic_result(report) for report in second.fixtures
    )

    near_ties = {
        report.fixture_id: tuple(tuple(group) for group in report.trace.selection["near_ties"])
        for report in first.fixtures
        if report.trace is not None
        and report.trace.selection is not None
        and report.trace.selection["near_ties"]
    }
    assert set(near_ties) == {"t25-quality-near-tie-equal-targets"}

    near_tie_report = next(
        report
        for report in first.fixtures
        if report.fixture_id == "t25-quality-near-tie-equal-targets"
    )
    assert near_tie_report.trace is not None
    assert near_tie_report.trace.selection is not None
    assert near_tie_report.trace.selection["tie_breaks"]
    assert near_tie_report.trace.selection["tie_breaks"][0]["criteria"] == [
        "lower_tail_risk",
        "lower_epistemic_uncertainty",
        "lower_irreversible_resource_cost",
        "stable_action_id",
    ]
