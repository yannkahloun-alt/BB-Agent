from pathlib import Path

from bb_agent.fixtures import ReviewStatus, load_fixture
from bb_agent.mechanics import load_builtin_mechanics
from bb_agent.results import ResultStatus
from bb_agent.validation import FixtureExpectations, run_validation_corpus

ROOT = Path(__file__).parent
FIXTURE_DIRS = (
    ROOT / "fixtures" / "ticket_24",
    ROOT / "fixtures" / "ticket_25",
)
REQUIRED_TAXONOMY = {
    "core_legality_affordability",
    "movement_path_zoc",
    "los_ranged_aoe",
    "obvious_offense_kill_secure",
    "survival_catastrophic_risk",
    "protection_formation",
    "elevation_positioning",
    "fatigue_resource_economy",
    "tempo_wait_end_turn",
    "control_disable_threat_priority",
    "uncertainty_no_cheat",
    "trace_failure_coverage",
}


def _load_corpus():
    fixtures = []
    for directory in FIXTURE_DIRS:
        for path in sorted(directory.glob("*.json")):
            loaded = load_fixture(path)
            assert loaded.status is ResultStatus.SUCCESS, loaded.problems
            assert loaded.value is not None
            fixtures.append(loaded.value)
    return tuple(fixtures)


def _contains_player_legal_debug_payload(value) -> bool:
    if isinstance(value, dict):
        if value.get("knowledge_class") == "DEBUG_GROUND_TRUTH":
            return True
        if value.get("authority") == "DEBUG_ORACLE":
            return True
        if "debug_ground_truth" in value and value["debug_ground_truth"] is not None:
            return True
        return any(_contains_player_legal_debug_payload(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_player_legal_debug_payload(item) for item in value)
    return False


def test_m1_closure_corpus_gates_and_coverage_health() -> None:
    fixtures = _load_corpus()
    assert len(fixtures) == 54
    assert all(fixture.metadata.review_status is ReviewStatus.PROMOTED for fixture in fixtures)

    authority_result = load_builtin_mechanics()
    assert authority_result.status is ResultStatus.SUCCESS
    assert authority_result.value is not None
    report = run_validation_corpus(authority_result.value, fixtures)

    assert report.passed
    assert report.coverage.total_fixtures == 54
    assert report.coverage.gated_fixtures == 54
    assert report.coverage.calibration_fixtures == 0
    assert report.coverage.safety_critical_fixtures == 10
    assert report.coverage.blocking_failure_count == 0
    assert report.coverage.review_finding_count == 0
    assert REQUIRED_TAXONOMY <= {name for name, _ in report.coverage.taxonomy_counts}
    assert sum(
        "uncertainty_no_cheat" in fixture.metadata.taxonomy for fixture in fixtures
    ) >= 8

    incomplete = []
    for fixture_report in report.fixtures:
        assert fixture_report.trace is not None
        status = fixture_report.trace.generation["decision_status"]
        if status != "INCOMPLETE_COVERAGE":
            continue
        fixture = next(
            item
            for item in fixtures
            if item.metadata.fixture_id == fixture_report.fixture_id
        )
        assert fixture.expectations is not None
        expectations = FixtureExpectations.from_json(fixture.expectations)
        assert expectations.expected_status == "INCOMPLETE_COVERAGE"
        assert not expectations.has_ranking_assertions
        diagnostics = fixture_report.trace.generation["coverage_diagnostics"]
        assert any(item["code"] == "EVALUATION_UNSUPPORTED" for item in diagnostics)
        incomplete.append(fixture_report.fixture_id)

    assert sorted(incomplete) == [
        "t24-core-coverage-impossible-aoo-geometry",
        "t24-core-coverage-multistep-aoo-costs",
        "t24-core-coverage-unknown-special",
        "t25-no-cheat-coverage-failure-health",
    ]


def test_m1_closure_player_legal_corpus_has_no_debug_leakage() -> None:
    fixtures = _load_corpus()
    player_legal = [
        fixture
        for fixture in fixtures
        if fixture.metadata.information_profile.value == "player_legal"
    ]
    assert len(player_legal) == 14
    assert all(
        not _contains_player_legal_debug_payload(fixture.state.to_dict())
        for fixture in player_legal
    )
