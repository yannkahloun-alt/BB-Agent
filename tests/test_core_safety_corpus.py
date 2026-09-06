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
EXPECTED_FIXTURE_COUNT = 32
EXPECTED_SAFETY_COUNT = 10
COVERAGE_FIXTURE_IDS = {
    "t24-core-coverage-impossible-aoo-geometry",
    "t24-core-coverage-multistep-aoo-costs",
    "t24-core-coverage-unknown-special",
}
KILL_SECURE_CORE_IDS = {
    "t24-safety-kill-secure-1hp",
    "t24-safety-kill-secure-5hp",
    "t24-safety-kill-secure-10hp",
    "t24-safety-kill-secure-15hp",
}
SAFETY_FIXTURE_IDS = {
    "t24-safety-double-aoo-20hp",
    "t24-safety-high-aoo-10hp",
    "t24-safety-high-damage-vs-protect-flank",
    "t24-safety-lethal-aoo-1hp",
    "t24-safety-lethal-aoo-5hp",
    "t24-safety-low-probability-lethal-aoo",
    "t24-safety-uphill-aoo-trap",
    "t24-safety-vacate-screen",
    "t24-safety-vacate-screen-1hp",
    "t24-safety-vacate-screen-5hp",
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


def _fixture(fixtures: tuple[FixtureEnvelope, ...], fixture_id: str) -> FixtureEnvelope:
    return next(item for item in fixtures if item.metadata.fixture_id == fixture_id)


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
        fixture.metadata.review_status is ReviewStatus.PROMOTED for fixture in fixtures
    )
    assert all(
        fixture.metadata.severity
        in {FixtureSeverity.CORE, FixtureSeverity.SAFETY_CRITICAL}
        for fixture in fixtures
    )

    safety_ids = {
        fixture.metadata.fixture_id
        for fixture in fixtures
        if fixture.metadata.severity is FixtureSeverity.SAFETY_CRITICAL
    }
    assert safety_ids == SAFETY_FIXTURE_IDS
    assert len(safety_ids) == EXPECTED_SAFETY_COUNT
    for fixture_id in KILL_SECURE_CORE_IDS:
        assert _fixture(fixtures, fixture_id).metadata.severity is FixtureSeverity.CORE

    taxonomy = {tag for fixture in fixtures for tag in fixture.metadata.taxonomy}
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
        assert fixture.state.annotations is None

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
    reports = {report.fixture_id: report for report in corpus.fixtures}

    for fixture_id in SAFETY_FIXTURE_IDS:
        fixture = _fixture(fixtures, fixture_id)
        report = reports[fixture_id]
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
        reports[fixture_id] for fixture_id in SAFETY_FIXTURE_IDS if "aoo" in fixture_id
    ]
    assert len(aoo_reports) == 6
    for report in aoo_reports:
        move = _evaluation_by_kind(report, ActionKind.MOVE_TO)
        assert move["evaluation"]["tail_risk"]["selection_penalty"] > 0
        assert (
            move["evaluation"]["features"]["friendly_harm"][
                "movement_interruption_probability"
            ]["expected"]
            > 0
        )


def test_affordability_range_target_and_terrain_boundaries_are_explicit() -> None:
    fixtures = _load_corpus()

    affordability = _fixture(fixtures, "t24-core-affordability-attack-excluded")
    actor = next(
        combatant
        for combatant in affordability.state.combatants
        if combatant.actor_id == affordability.state.decision.active_actor_id
    )
    assert actor.resources.action_points.value == 3
    assert any(skill.skill_id == "actives.chop" for skill in actor.skills)
    assert all(
        action.kind is ActionKind.WAIT
        for action in affordability.state.action_affordances.actions
    )

    ranged = _fixture(fixtures, "t24-core-range-attack-excluded")
    ranged_actor = next(
        combatant
        for combatant in ranged.state.combatants
        if combatant.actor_id == ranged.state.decision.active_actor_id
    )
    hostile = next(
        combatant
        for combatant in ranged.state.combatants
        if combatant.actor_id == "enemy"
    )
    actor_tile = next(
        tile
        for tile in ranged.state.tiles
        if tile.tile_id == ranged_actor.position.value
    )
    hostile_tile = next(
        tile for tile in ranged.state.tiles if tile.tile_id == hostile.position.value
    )
    assert actor_tile.coordinate.distance_to(hostile_tile.coordinate) > 1
    assert all(
        action.kind is not ActionKind.USE_SKILL
        for action in ranged.state.action_affordances.actions
    )

    target = _fixture(fixtures, "t24-core-target-affordance-integrity")
    attack = next(
        action
        for action in target.state.action_affordances.actions
        if action.kind is ActionKind.USE_SKILL
    )
    assert attack.target_actor_id == "enemy"
    assert attack.target_kind is not None and attack.target_kind.value == "ACTOR"
    assert attack.preview.affected_tile_ids is not None
    assert attack.preview.affected_tile_ids.value == ("east",)

    terrain = _fixture(fixtures, "t24-core-terrain-resolved-move-cost")
    move = next(
        action
        for action in terrain.state.action_affordances.actions
        if action.kind is ActionKind.MOVE_TO
    )
    destination = next(
        tile for tile in terrain.state.tiles if tile.tile_id == move.destination_tile_id
    )
    assert destination.terrain.value == "swamp"
    assert move.ap_cost is not None and move.ap_cost.value == 4
    assert move.fatigue_cost is not None and move.fatigue_cost.value == 8


def test_high_damage_temptation_commits_turn_and_loses_to_flank_protection() -> None:
    fixtures = _load_corpus()
    fixture = _fixture(fixtures, "t24-safety-high-damage-vs-protect-flank")
    actor = next(
        combatant
        for combatant in fixture.state.combatants
        if combatant.actor_id == fixture.state.decision.active_actor_id
    )
    assert actor.resources.action_points.value == 4

    corpus = run_validation_corpus(_authority(), (fixture,))
    assert corpus.passed, corpus.blocking_failures
    report = corpus.fixtures[0]
    assert report.trace is not None
    assert report.trace.selection is not None

    attack = _evaluation_by_kind(report, ActionKind.USE_SKILL)
    move = _evaluation_by_kind(report, ActionKind.MOVE_TO)
    assert attack["action"]["ap_cost"]["value"] == 4
    assert move["action"]["ap_cost"]["value"] == 2
    assert (
        attack["evaluation"]["features"]["resources"]["remaining_action_points"][
            "expected"
        ]
        == 0
    )
    assert (
        move["evaluation"]["features"]["resources"]["remaining_action_points"][
            "expected"
        ]
        == 2
    )
    assert (
        attack["evaluation"]["features"]["enemy_effect"]["expected_hp_damage"][
            "expected"
        ]
        > 20
    )
    assert (
        move["evaluation"]["features"]["formation"]["created_direct_screen_links"][
            "expected"
        ]
        == 1
    )
    assert (
        move["evaluation"]["features"]["position"]["elevation_change"]["expected"] == 2
    )
    assert report.trace.selection["chosen_action_id"] == move["action_id"]
