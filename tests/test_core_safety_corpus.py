from pathlib import Path

from bb_agent.fixtures import (
    FixtureEnvelope,
    FixtureSeverity,
    ReviewStatus,
    load_fixture,
)
from bb_agent.results import ResultStatus
from bb_agent.tactical_state import ActionKind
from bb_agent.validation import FixtureExpectations, run_validation_corpus
from test_mechanics import _authority

CORPUS_DIR = Path(__file__).parent / "fixtures" / "ticket_24"
EXPECTED_FIXTURE_COUNT = 25
EXPECTED_SAFETY_COUNT = 11
COVERAGE_FIXTURE_IDS = {
    "t24-core-coverage-impossible-aoo-geometry",
    "t24-core-coverage-multistep-aoo-costs",
    "t24-core-coverage-unknown-special",
}
REQUIRED_TAXONOMY = {
    "core_legality_affordability",
    "obvious_offense_kill_secure",
    "movement_path_zoc",
    "los_ranged_aoe",
    "elevation_positioning",
    "fatigue_resource_economy",
    "tempo_wait_end_turn",
    "protection_formation",
    "survival_catastrophic_risk",
    "trace_failure_coverage",
}
UPSTREAM_RULES_REVISION = "162f498ac7c49b4c317bbf54718a595ecef6a65a"


def _load_corpus() -> tuple[FixtureEnvelope, ...]:
    fixtures = []
    for path in sorted(CORPUS_DIR.glob("*.json")):
        loaded = load_fixture(path)
        assert loaded.status is ResultStatus.SUCCESS, loaded.problems
        assert loaded.value is not None
        fixtures.append(loaded.value)
    return tuple(fixtures)


def _evaluation_by_kind(report, kind: ActionKind):
    assert report.trace is not None
    return next(
        record
        for record in report.trace.evaluations
        if record["action"]["kind"] == kind.value
    )


def test_ticket_24_corpus_is_promoted_gated_and_harness_green() -> None:
    fixtures = _load_corpus()

    assert len(fixtures) == EXPECTED_FIXTURE_COUNT
    assert len({fixture.metadata.fixture_id for fixture in fixtures}) == len(fixtures)
    assert all(
        fixture.metadata.review_status is ReviewStatus.PROMOTED
        for fixture in fixtures
    )
    assert all(
        fixture.metadata.severity
        in {FixtureSeverity.CORE, FixtureSeverity.SAFETY_CRITICAL}
        for fixture in fixtures
    )
    assert (
        sum(
            fixture.metadata.severity is FixtureSeverity.SAFETY_CRITICAL
            for fixture in fixtures
        )
        == EXPECTED_SAFETY_COUNT
    )

    taxonomy = {
        tag for fixture in fixtures for tag in fixture.metadata.taxonomy
    }
    assert REQUIRED_TAXONOMY <= taxonomy

    for fixture in fixtures:
        provenance = fixture.metadata.provenance
        assert provenance is not None
        assert provenance["ticket"] == 24
        assert provenance["frozen_specs"] == ["#10", "#13"]
        assert provenance["mechanics_source"] == (
            "src/bb_agent/data/catalog.v1.json + manifest.v1.json"
        )
        assert provenance["catalog_revision"] == UPSTREAM_RULES_REVISION
        assert provenance["evidence"]

    report = run_validation_corpus(_authority(), fixtures)
    assert report.passed, report.blocking_failures
    assert report.coverage.total_fixtures == EXPECTED_FIXTURE_COUNT
    assert report.coverage.gated_fixtures == EXPECTED_FIXTURE_COUNT
    assert report.coverage.calibration_fixtures == 0
    assert report.coverage.safety_critical_fixtures == EXPECTED_SAFETY_COUNT
    assert report.coverage.blocking_failure_count == 0


def test_ticket_24_safety_and_coverage_cases_fail_closed() -> None:
    fixtures = _load_corpus()
    corpus = run_validation_corpus(_authority(), fixtures)
    reports = {
        report.fixture_id: report for report in corpus.fixtures
    }

    for fixture in fixtures:
        report = reports[fixture.metadata.fixture_id]
        if fixture.metadata.severity is FixtureSeverity.SAFETY_CRITICAL:
            assert report.trace is not None
            assert report.trace.selection is not None
            expectations = FixtureExpectations.from_json(fixture.expectations)
            assert expectations.forbidden_top1
            assert (
                report.trace.selection["chosen_action_id"]
                not in expectations.forbidden_top1
            )

    for fixture_id in COVERAGE_FIXTURE_IDS:
        report = reports[fixture_id]
        assert report.trace is not None
        assert report.trace.generation["decision_status"] == "INCOMPLETE_COVERAGE"
        assert report.trace.selection is None
        assert report.trace.evaluations == ()
        assert report.trace.generation["legal_candidates"]
        assert any(
            problem["code"] == "EVALUATION_UNSUPPORTED"
            for problem in report.trace.generation["coverage_diagnostics"]
        )

    aoo_reports = [
        report
        for fixture_id, report in reports.items()
        if fixture_id.startswith("t24-safety-") and "aoo" in fixture_id
    ]
    assert len(aoo_reports) == 5
    for report in aoo_reports:
        move = _evaluation_by_kind(report, ActionKind.MOVE_TO)
        assert move["evaluation"]["tail_risk"]["selection_penalty"] > 0
        assert (
            move["evaluation"]["features"]["friendly_harm"]
            ["movement_interruption_probability"]["expected"]
            > 0
        )


def test_high_damage_temptation_loses_to_immediate_flank_protection() -> None:
    fixture = next(
        item
        for item in _load_corpus()
        if item.metadata.fixture_id == "t24-safety-high-damage-vs-protect-flank"
    )
    corpus = run_validation_corpus(_authority(), (fixture,))
    assert corpus.passed, corpus.blocking_failures
    report = corpus.fixtures[0]
    assert report.trace is not None
    assert report.trace.selection is not None

    attack = _evaluation_by_kind(report, ActionKind.USE_SKILL)
    move = _evaluation_by_kind(report, ActionKind.MOVE_TO)
    assert (
        attack["evaluation"]["features"]["enemy_effect"]
        ["expected_hp_damage"]["expected"]
        > 20
    )
    assert (
        move["evaluation"]["features"]["formation"]
        ["created_direct_screen_links"]["expected"]
        == 1
    )
    assert (
        move["evaluation"]["features"]["position"]
        ["elevation_change"]["expected"]
        == 2
    )
    assert report.trace.selection["chosen_action_id"] == move["action_id"]
