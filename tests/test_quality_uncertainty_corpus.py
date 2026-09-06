from dataclasses import fields, is_dataclass
from pathlib import Path

from bb_agent.evaluator import UnitValuePolicy
from bb_agent.fixtures import FixtureEnvelope, ReviewStatus, load_fixture
from bb_agent.results import ResultStatus
from bb_agent.tactical_state import InformationProfile, KnowledgeClass, KnownValue
from bb_agent.validation import run_fixture_validation, run_validation_corpus
from test_mechanics import _authority

ROOT = Path(__file__).parent
TICKET_24_DIR = ROOT / "fixtures" / "ticket_24"
TICKET_25_DIR = ROOT / "fixtures" / "ticket_25"
EXPECTED_TICKET_25_COUNT = 21
EXPECTED_COMBINED_COUNT = 54
EXPECTED_SAFETY_COUNT = 10
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


def _load_directory(path: Path) -> tuple[FixtureEnvelope, ...]:
    fixtures = []
    for fixture_path in sorted(path.glob("*.json")):
        loaded = load_fixture(fixture_path)
        assert loaded.status is ResultStatus.SUCCESS, loaded.problems
        assert loaded.value is not None
        fixtures.append(loaded.value)
    return tuple(fixtures)


def _fixture(fixtures: tuple[FixtureEnvelope, ...], fixture_id: str) -> FixtureEnvelope:
    return next(item for item in fixtures if item.metadata.fixture_id == fixture_id)


def _contains_debug_ground_truth(value) -> bool:
    if isinstance(value, KnownValue):
        return value.knowledge_class is KnowledgeClass.DEBUG_GROUND_TRUTH
    if is_dataclass(value):
        return any(
            _contains_debug_ground_truth(getattr(value, field.name))
            for field in fields(value)
        )
    if isinstance(value, dict):
        return any(_contains_debug_ground_truth(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return any(_contains_debug_ground_truth(item) for item in value)
    return False


def _evaluation_by_kind(report, kind: str):
    assert report.trace is not None
    return next(
        record
        for record in report.trace.evaluations
        if record["action"]["kind"] == kind
    )


def test_ticket_25_completes_frozen_m1_corpus_counts_and_taxonomy() -> None:
    ticket_24 = _load_directory(TICKET_24_DIR)
    ticket_25 = _load_directory(TICKET_25_DIR)
    combined = ticket_24 + ticket_25

    assert len(ticket_25) == EXPECTED_TICKET_25_COUNT
    assert len(combined) == EXPECTED_COMBINED_COUNT
    assert len({fixture.metadata.fixture_id for fixture in combined}) == len(combined)
    assert all(
        fixture.metadata.review_status is ReviewStatus.PROMOTED for fixture in combined
    )

    uncertainty = tuple(
        fixture
        for fixture in ticket_25
        if "uncertainty_no_cheat" in fixture.metadata.taxonomy
    )
    assert len(uncertainty) >= 8

    taxonomy = {tag for fixture in combined for tag in fixture.metadata.taxonomy}
    assert REQUIRED_TAXONOMY <= taxonomy

    report = run_validation_corpus(_authority(), combined)
    assert report.passed, [
        (fixture.fixture_id, fixture.blocking_failures)
        for fixture in report.fixtures
        if fixture.blocking_failures
    ]
    assert report.coverage.total_fixtures == EXPECTED_COMBINED_COUNT
    assert report.coverage.gated_fixtures == EXPECTED_COMBINED_COUNT
    assert report.coverage.calibration_fixtures == 0
    assert report.coverage.safety_critical_fixtures == EXPECTED_SAFETY_COUNT
    assert report.coverage.blocking_failure_count == 0


def test_player_legal_debug_pairs_share_capture_without_debug_truth_leakage() -> None:
    fixtures = _load_directory(TICKET_25_DIR)

    stable_player = _fixture(fixtures, "t25-no-cheat-stable-player")
    stable_debug = _fixture(fixtures, "t25-no-cheat-stable-debug")
    flip_player = _fixture(fixtures, "t25-no-cheat-flip-player")
    flip_debug_low = _fixture(fixtures, "t25-no-cheat-flip-debug-low")
    flip_debug_high = _fixture(fixtures, "t25-no-cheat-flip-debug-high")

    assert stable_player.state.information_profile is InformationProfile.PLAYER_LEGAL
    assert stable_debug.state.information_profile is InformationProfile.OMNISCIENT_DEBUG
    assert stable_player.state.raw_capture_id == stable_debug.state.raw_capture_id
    assert not _contains_debug_ground_truth(stable_player.state)

    assert flip_player.state.information_profile is InformationProfile.PLAYER_LEGAL
    assert (
        flip_debug_low.state.information_profile is InformationProfile.OMNISCIENT_DEBUG
    )
    assert (
        flip_debug_high.state.information_profile is InformationProfile.OMNISCIENT_DEBUG
    )
    assert flip_player.state.raw_capture_id == flip_debug_low.state.raw_capture_id
    assert flip_player.state.raw_capture_id == flip_debug_high.state.raw_capture_id
    assert not _contains_debug_ground_truth(flip_player.state)

    player_report = run_fixture_validation(_authority(), flip_player)
    low_report = run_fixture_validation(_authority(), flip_debug_low)
    high_report = run_fixture_validation(_authority(), flip_debug_high)
    assert player_report.passed
    assert low_report.passed
    assert high_report.passed
    assert player_report.trace is not None and player_report.trace.selection is not None
    assert low_report.trace is not None and low_report.trace.selection is not None
    assert high_report.trace is not None and high_report.trace.selection is not None
    assert player_report.trace.selection["information_sensitive"] is True
    assert low_report.trace.selection["information_sensitive"] is False
    assert high_report.trace.selection["information_sensitive"] is False
    assert (
        low_report.trace.selection["chosen_action_id"]
        != high_report.trace.selection["chosen_action_id"]
    )


def test_displayed_hit_chance_is_legal_without_hidden_enemy_defense() -> None:
    fixture = _fixture(
        _load_directory(TICKET_25_DIR),
        "t25-no-cheat-preview-hidden-defense",
    )
    enemy = next(
        actor for actor in fixture.state.combatants if actor.actor_id == "enemy"
    )
    attack = next(
        action
        for action in fixture.state.action_affordances.actions
        if action.target_actor_id == "enemy"
    )

    assert fixture.state.information_profile is InformationProfile.PLAYER_LEGAL
    assert attack.preview.displayed_hit_chance is not None
    assert attack.preview.displayed_hit_chance.value == 67
    assert not _contains_debug_ground_truth(fixture.state)
    assert not any(
        stat.stat_id == "melee_defense"
        and stat.value.knowledge_class is KnowledgeClass.DEBUG_GROUND_TRUTH
        for stat in enemy.tactical_stats
    )


def test_aleatory_aoo_spread_is_not_epistemic_uncertainty() -> None:
    fixture = _fixture(
        _load_directory(TICKET_25_DIR),
        "t25-no-cheat-aleatory-only-debug",
    )
    report = run_fixture_validation(_authority(), fixture)

    assert report.passed, report.blocking_failures
    move = _evaluation_by_kind(report, "MOVE_TO")
    harm = move["evaluation"]["features"]["friendly_harm"]["expected_self_hp_damage"]
    assert harm["maximum"] > harm["minimum"]
    assert move["evaluation"]["uncertainty_span"] == 0
    assert report.trace is not None and report.trace.selection is not None
    assert report.trace.selection["information_sensitive"] is False


def test_unit_value_policy_pair_changes_loss_cost_without_state_mutation() -> None:
    fixtures = _load_directory(TICKET_25_DIR)
    default_fixture = _fixture(fixtures, "t25-unit-value-default")
    high_fixture = _fixture(fixtures, "t25-unit-value-high")

    assert default_fixture.state.state_id == high_fixture.state.state_id
    assert default_fixture.state == high_fixture.state

    default_report = run_fixture_validation(_authority(), default_fixture)
    high_policy = UnitValuePolicy(
        version="ticket-25-high-strategic-value.v1",
        actor_values=(("brother", 4.0),),
    )
    high_report = run_fixture_validation(
        _authority(),
        high_fixture,
        unit_value_policy=high_policy,
    )
    assert default_report.passed, default_report.blocking_failures
    assert high_report.passed, high_report.blocking_failures

    default_move = _evaluation_by_kind(default_report, "MOVE_TO")
    high_move = _evaluation_by_kind(high_report, "MOVE_TO")
    default_tail = default_move["evaluation"]["tail_risk"]
    high_tail = high_move["evaluation"]["tail_risk"]
    assert default_tail["unit_value"] == 1
    assert high_tail["unit_value"] == 4
    assert high_tail["selection_penalty"] > default_tail["selection_penalty"]
    assert default_report.trace is not None and high_report.trace is not None
    assert default_report.trace.input["state_id"] == high_report.trace.input["state_id"]
    assert (
        default_report.trace.engine["unit_value_policy_fingerprint"]
        != high_report.trace.engine["unit_value_policy_fingerprint"]
    )
