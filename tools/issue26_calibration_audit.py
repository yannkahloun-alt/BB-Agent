from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import bb_agent.evaluator as evaluator  # noqa: E402
from bb_agent.evaluator import (  # noqa: E402
    DEFAULT_EVALUATION_PROFILE,
    DEFAULT_UNIT_VALUE_POLICY,
)
from bb_agent.fixtures import load_fixture  # noqa: E402
from bb_agent.results import ResultStatus  # noqa: E402
from bb_agent.validation import run_validation_corpus  # noqa: E402
from test_mechanics import _authority  # noqa: E402


def load_corpus():
    fixtures = []
    for directory in (ROOT / "tests/fixtures/ticket_24", ROOT / "tests/fixtures/ticket_25"):
        for path in sorted(directory.glob("*.json")):
            result = load_fixture(path)
            assert result.status is ResultStatus.SUCCESS, result.problems
            assert result.value is not None
            fixtures.append(result.value)
    return tuple(fixtures)


def failures(report):
    return [
        (fixture.fixture_id, tuple(item.assertion_id for item in fixture.blocking_failures))
        for fixture in report.fixtures
        if fixture.blocking_failures
    ]


def rankings(report):
    values = {}
    for fixture in report.fixtures:
        if fixture.trace is None or fixture.trace.selection is None:
            continue
        values[fixture.fixture_id] = (
            tuple(fixture.trace.selection["ranking"]),
            fixture.trace.selection["chosen_action_id"],
            tuple(
                (record["action_id"], record["evaluation"]["ranking_value"])
                for record in fixture.trace.evaluations
            ),
        )
    return values


def dedup_resource_component(features, profile):
    scales = profile.scales
    template_count = features.future_capacity.current_cost_template_count
    template_scale = max(1.0, float(template_count))
    return evaluator._component(
        "resource_fat_future_capacity",
        (
            evaluator._normalized(features.resources.remaining_action_points, scales.action_points),
            evaluator._normalized(features.resources.fatigue_headroom, scales.fatigue_headroom),
            evaluator._normalized(
                features.future_capacity.ap_fat_feasible_template_count,
                template_scale,
            ),
            evaluator._normalized(
                evaluator.MetricRange.exact(features.resources.ammo_consumed),
                scales.resource_units,
                -1.0,
            ),
            evaluator._normalized(
                evaluator.MetricRange.exact(features.resources.charges_consumed),
                scales.resource_units,
                -1.0,
            ),
        ),
        profile.weights.resource_future_capacity,
    )


def main() -> None:
    authority = _authority()
    fixtures = load_corpus()
    baseline = run_validation_corpus(authority, fixtures)
    assert baseline.passed, failures(baseline)
    baseline_rankings = rankings(baseline)

    print("CALIBRATION_PROVENANCE")
    print("fixture_count", len(fixtures))
    print("python", platform.python_version())
    print("platform", platform.platform())
    print("machine", platform.machine())
    print("cpu", platform.processor() or os.environ.get("RUNNER_ARCH", "unknown"))
    print("profile_version", DEFAULT_EVALUATION_PROFILE.version)
    print("profile_fingerprint", DEFAULT_EVALUATION_PROFILE.fingerprint)
    print("unit_value_version", DEFAULT_UNIT_VALUE_POLICY.version)
    print("unit_value_fingerprint", DEFAULT_UNIT_VALUE_POLICY.fingerprint)
    print("median_ns", baseline.coverage.median_decision_ns)
    print("p95_ns", baseline.coverage.p95_decision_ns)
    print("max_ns", baseline.coverage.max_decision_ns)

    near_ties = []
    minimum_gap = None
    for fixture in baseline.fixtures:
        trace = fixture.trace
        if trace is None or trace.selection is None:
            continue
        groups = trace.selection.get("near_ties", ())
        if groups:
            near_ties.append((fixture.fixture_id, groups))
        scores = sorted(
            (record["evaluation"]["ranking_value"] for record in trace.evaluations),
            reverse=True,
        )
        if len(scores) >= 2:
            gap = scores[0] - scores[1]
            if gap > 1e-12 and (minimum_gap is None or gap < minimum_gap[1]):
                minimum_gap = (fixture.fixture_id, gap)
    print("near_tie_fixtures", near_ties)
    print("minimum_nonzero_top_gap", minimum_gap)

    original = evaluator._resource_component
    evaluator._resource_component = dedup_resource_component
    try:
        dedup = run_validation_corpus(authority, fixtures)
    finally:
        evaluator._resource_component = original

    print("DEDUP_GATE_FAILURES", failures(dedup))
    dedup_rankings = rankings(dedup)
    changed = []
    score_only = []
    for fixture_id, before in baseline_rankings.items():
        after = dedup_rankings[fixture_id]
        if before[:2] != after[:2]:
            changed.append((fixture_id, before[:2], after[:2]))
        elif before[2] != after[2]:
            score_only.append(fixture_id)
    print("DEDUP_RANKING_CHANGES", changed)
    print("DEDUP_SCORE_ONLY_COUNT", len(score_only))
    print("DEDUP_SCORE_ONLY_FIXTURES", score_only)
    print("DEDUP_TIMING_NS", dedup.coverage.median_decision_ns, dedup.coverage.p95_decision_ns, dedup.coverage.max_decision_ns)


if __name__ == "__main__":
    main()
