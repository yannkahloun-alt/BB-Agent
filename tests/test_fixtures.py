import json
from dataclasses import fields, replace
from pathlib import Path

import pytest

from bb_agent.fixtures import (
    FixtureEnvelope,
    FixtureMetadata,
    FixtureSeverity,
    FixtureSourceKind,
    ReviewStatus,
    load_fixture,
    save_fixture,
    validate_fixture_pair,
)
from bb_agent.results import ErrorCode, ResultStatus
from bb_agent.tactical_state import (
    AffordanceCompleteness,
    AffordanceProvenance,
    InformationProfile,
    KnowledgeClass,
    KnownValue,
    Representation,
    ResolutionAuthority,
    SkillState,
    TacticalState,
)
from test_tactical_state import _state


def _fixture(
    profile: InformationProfile = InformationProfile.PLAYER_LEGAL,
) -> FixtureEnvelope:
    state = _state(profile)
    return FixtureEnvelope.create(
        metadata=FixtureMetadata(
            fixture_id=f"preview-{profile.value}",
            source_kind=FixtureSourceKind.HANDCRAFTED,
            taxonomy=("uncertainty_no_cheat", "action_preview"),
            severity=FixtureSeverity.CORE,
            scenario_intent="Resolved preview remains usable without hidden defense.",
            ruleset_content_fingerprint=state.ruleset.content_fingerprint,
            information_profile=profile,
            affordance_completeness=AffordanceCompleteness.COMPLETE,
            expectation_version="expectations.v1",
            review_status=ReviewStatus.REVIEWED,
            provenance={"author": "BB-Agent", "basis": "handcrafted"},
        ),
        state=state,
        expectations={
            "acceptable_top1": [state.action_affordances.actions[0].action_id]
        },
        oracle_annotations={"note": "not a decision input"},
    )


def _with_state(fixture: FixtureEnvelope, **changes: object) -> FixtureEnvelope:
    values = {
        item.name: getattr(fixture.state, item.name) for item in fields(TacticalState)
    }
    values.update(changes)
    values["state_id"] = ""
    state = TacticalState.create(**values)
    return FixtureEnvelope.create(
        metadata=fixture.metadata,
        state=state,
        expectations=fixture.expectations,
        oracle_annotations=fixture.oracle_annotations,
    )


def _with_enemy_hit_points(
    fixture: FixtureEnvelope, value: KnownValue
) -> FixtureEnvelope:
    enemy = next(
        actor for actor in fixture.state.combatants if actor.actor_id == "enemy"
    )
    changed_enemy = replace(enemy, resources=replace(enemy.resources, hit_points=value))
    return _with_state(
        fixture,
        combatants=tuple(
            changed_enemy if actor.actor_id == "enemy" else actor
            for actor in fixture.state.combatants
        ),
    )


def _with_actions(
    fixture: FixtureEnvelope, actions: tuple[object, ...]
) -> FixtureEnvelope:
    return _with_state(
        fixture,
        action_affordances=replace(
            fixture.state.action_affordances,
            captured_for_state_id="",
            actions=actions,
        ),
    )


def test_fixture_round_trip_is_canonical_and_replayable(tmp_path: Path) -> None:
    fixture = _fixture()
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"

    assert save_fixture(first_path, fixture).status is ResultStatus.SUCCESS
    loaded = load_fixture(first_path)
    assert loaded.status is ResultStatus.SUCCESS
    assert loaded.value is not None
    assert save_fixture(second_path, loaded.value).status is ResultStatus.SUCCESS

    assert first_path.read_bytes() == second_path.read_bytes()
    replay = loaded.value.replay_input()
    assert replay.state_id == fixture.state.state_id
    assert replay.state.annotations is None
    assert replay.state.normalized() == replay.state
    assert replay.information_profile is InformationProfile.PLAYER_LEGAL


def test_expectations_and_oracle_annotations_do_not_change_decision_identity() -> None:
    fixture = _fixture()
    changed = replace(
        fixture,
        expectations={"forbidden_top1": ["anything"]},
        oracle_annotations={"hidden_enemy_defense": 999},
    )

    assert (
        changed.replay_input().decision_identity
        == fixture.replay_input().decision_identity
    )
    assert changed.state_hash == fixture.state_hash
    assert changed.replay_input().state.annotations is None


def test_paired_legal_and_debug_views_link_capture_but_keep_distinct_identity() -> None:
    legal = _fixture()
    debug = _fixture(InformationProfile.OMNISCIENT_DEBUG)

    result = validate_fixture_pair(legal, debug)

    assert result.status is ResultStatus.SUCCESS
    assert legal.state.raw_capture_id == debug.state.raw_capture_id
    assert legal.state.state_id != debug.state.state_id
    assert (
        legal.replay_input().state.action_affordances.actions[0].debug_ground_truth
        is None
    )
    assert debug.replay_input().state.action_affordances.actions[
        0
    ].debug_ground_truth == {"enemy_melee_defense": 12}
    assert debug.replay_input().state.normalized() == debug.replay_input().state


def test_pair_rejects_different_raw_capture() -> None:
    legal = _fixture()
    debug = _fixture(InformationProfile.OMNISCIENT_DEBUG)
    changed_state = replace(debug.state, raw_capture_id="capture-other")
    changed = replace(debug, state=changed_state)

    result = validate_fixture_pair(legal, changed)

    assert result.status is ResultStatus.VALIDATION_FAILURE
    assert result.problems[0].code is ErrorCode.FIXTURE_PAIR_MISMATCH


def test_pair_rejects_unrelated_capture_stable_identity() -> None:
    legal = _fixture()
    debug = _fixture(InformationProfile.OMNISCIENT_DEBUG)

    changed_battle = _with_state(
        debug, battle=replace(debug.state.battle, battle_id="other-battle")
    )
    changed_decision = _with_state(
        debug,
        decision=replace(debug.state.decision, decision_index=999),
    )
    changed_generation = "other-generation"
    changed_actions = tuple(
        replace(action, source_generation=changed_generation)
        for action in debug.state.action_affordances.actions
    )
    changed_source = _with_state(
        debug,
        action_affordances=replace(
            debug.state.action_affordances,
            captured_for_state_id="",
            source_generation=changed_generation,
            actions=changed_actions,
        ),
    )

    for changed in (changed_battle, changed_decision, changed_source):
        result = validate_fixture_pair(legal, changed)
        assert result.status is ResultStatus.VALIDATION_FAILURE
        assert result.problems[0].code is ErrorCode.FIXTURE_PAIR_MISMATCH


def test_pair_rejects_changed_player_visible_fact_but_allows_debug_enrichment() -> None:
    legal = _fixture()
    debug = _fixture(InformationProfile.OMNISCIENT_DEBUG)
    active = next(
        actor for actor in debug.state.combatants if actor.actor_id == "brother"
    )
    changed_active = replace(
        active,
        resources=replace(active.resources, hit_points=KnownValue.exact(59)),
    )
    changed_visible = _with_state(
        debug,
        combatants=tuple(
            changed_active if actor.actor_id == "brother" else actor
            for actor in debug.state.combatants
        ),
    )

    rejected = validate_fixture_pair(legal, changed_visible)
    assert rejected.status is ResultStatus.VALIDATION_FAILURE
    assert rejected.problems[0].code is ErrorCode.FIXTURE_PAIR_MISMATCH
    assert validate_fixture_pair(legal, debug).status is ResultStatus.SUCCESS


def test_pair_accepts_contained_debug_truth_and_rejects_contradiction() -> None:
    legal = _fixture()
    debug = _fixture(InformationProfile.OMNISCIENT_DEBUG)

    legal_range = _with_enemy_hit_points(
        legal,
        KnownValue(
            Representation.RANGE,
            KnowledgeClass.OBSERVED,
            minimum=40,
            maximum=60,
        ),
    )
    contained = _with_enemy_hit_points(
        debug,
        KnownValue.exact(50, KnowledgeClass.DEBUG_GROUND_TRUTH),
    )
    outside = _with_enemy_hit_points(
        debug,
        KnownValue.exact(30, KnowledgeClass.DEBUG_GROUND_TRUTH),
    )

    assert validate_fixture_pair(legal_range, contained).status is ResultStatus.SUCCESS
    rejected = validate_fixture_pair(legal_range, outside)
    assert rejected.status is ResultStatus.VALIDATION_FAILURE
    assert rejected.problems[0].code is ErrorCode.FIXTURE_PAIR_MISMATCH


def _exact(value: int, *, debug: bool = False) -> KnownValue:
    if debug:
        return KnownValue.exact(value, KnowledgeClass.DEBUG_GROUND_TRUTH)
    return KnownValue(
        Representation.EXACT,
        KnowledgeClass.DERIVED,
        value=value,
        basis=("player-visible",),
    )


def _range(minimum: int, maximum: int, *, debug: bool = False) -> KnownValue:
    return KnownValue(
        Representation.RANGE,
        KnowledgeClass.DEBUG_GROUND_TRUTH if debug else KnowledgeClass.OBSERVED,
        minimum=minimum,
        maximum=maximum,
    )


def _set(*values: int, debug: bool = False) -> KnownValue:
    return KnownValue(
        Representation.SET,
        KnowledgeClass.DEBUG_GROUND_TRUTH if debug else KnowledgeClass.OBSERVED,
        candidates=values,
    )


def _distribution(*entries: tuple[int, float], debug: bool = False) -> KnownValue:
    return KnownValue(
        Representation.DISTRIBUTION,
        KnowledgeClass.DEBUG_GROUND_TRUTH if debug else KnowledgeClass.OBSERVED,
        distribution=entries,
    )


@pytest.mark.parametrize(
    ("legal_value", "debug_value", "accepted"),
    (
        (KnownValue.unknown(), _exact(50, debug=True), True),
        (KnownValue.unknown(), _range(40, 60, debug=True), True),
        (KnownValue.unknown(), _set(40, 60, debug=True), True),
        (KnownValue.unknown(), _distribution((40, 0.5), (60, 0.5), debug=True), True),
        (_exact(50), _exact(50, debug=True), True),
        (_exact(50), _range(50, 50, debug=True), True),
        (_exact(50), _set(50, debug=True), True),
        (_exact(50), _distribution((50, 1.0), (60, 0.0), debug=True), True),
        (_range(40, 60), _exact(50, debug=True), True),
        (_range(40, 60), _range(45, 55, debug=True), True),
        (_range(40, 60), _set(40, 50, 60, debug=True), True),
        (_range(40, 60), _distribution((45, 0.5), (55, 0.5), debug=True), True),
        (_set(40, 50, 60), _exact(50, debug=True), True),
        (_set(40, 50, 60), _range(50, 50, debug=True), True),
        (_set(40, 50, 60), _set(40, 60, debug=True), True),
        (
            _set(40, 50, 60),
            _distribution((40, 0.5), (60, 0.5), debug=True),
            True,
        ),
        (_distribution((40, 0.5), (60, 0.5)), _exact(40, debug=True), True),
        (
            _distribution((40, 0.5), (60, 0.5)),
            _range(60, 60, debug=True),
            True,
        ),
        (
            _distribution((40, 0.5), (60, 0.5)),
            _set(40, 60, debug=True),
            True,
        ),
        (
            _distribution((40, 0.5), (60, 0.5)),
            _distribution((40, 1.0), (50, 0.0), debug=True),
            True,
        ),
        (_exact(50), _range(49, 50, debug=True), False),
        (_range(40, 60), _set(40, 70, debug=True), False),
        (_range(40, 60), _distribution((50, 0.5), (70, 0.5), debug=True), False),
        (_set(40, 50, 60), _range(40, 50, debug=True), False),
        (_set(40, 50, 60), _distribution((40, 0.5), (55, 0.5), debug=True), False),
        (_distribution((40, 0.5), (60, 0.5)), _exact(50, debug=True), False),
    ),
)
def test_pair_debug_domain_must_be_subset_of_legal_domain(
    legal_value: KnownValue, debug_value: KnownValue, accepted: bool
) -> None:
    legal = _with_enemy_hit_points(_fixture(), legal_value)
    debug = _with_enemy_hit_points(
        _fixture(InformationProfile.OMNISCIENT_DEBUG), debug_value
    )

    result = validate_fixture_pair(legal, debug)

    assert (result.status is ResultStatus.SUCCESS) is accepted
    if not accepted:
        assert result.problems[0].code is ErrorCode.FIXTURE_PAIR_MISMATCH


def test_pair_allows_explicitly_marked_debug_only_hidden_skill() -> None:
    legal = _fixture()
    debug = _fixture(InformationProfile.OMNISCIENT_DEBUG)
    enemy = next(actor for actor in debug.state.combatants if actor.actor_id == "enemy")
    hidden_skill = SkillState(
        "skill.hidden",
        KnownValue.exact(True, KnowledgeClass.DEBUG_GROUND_TRUTH),
        enabled=KnownValue.exact(True, KnowledgeClass.DEBUG_GROUND_TRUTH),
    )
    enriched_enemy = replace(enemy, skills=(*enemy.skills, hidden_skill))
    enriched = _with_state(
        debug,
        combatants=tuple(
            enriched_enemy if actor.actor_id == "enemy" else actor
            for actor in debug.state.combatants
        ),
    )

    assert validate_fixture_pair(legal, enriched).status is ResultStatus.SUCCESS

    unmarked_enemy = replace(
        enemy,
        skills=(SkillState("skill.visible", KnownValue.exact(True)),),
    )
    unmarked = _with_state(
        debug,
        combatants=tuple(
            unmarked_enemy if actor.actor_id == "enemy" else actor
            for actor in debug.state.combatants
        ),
    )
    rejected = validate_fixture_pair(legal, unmarked)
    assert rejected.status is ResultStatus.VALIDATION_FAILURE
    assert rejected.problems[0].code is ErrorCode.FIXTURE_PAIR_MISMATCH


def test_pair_rejects_changed_action_provenance_and_resolution_authority() -> None:
    legal = _fixture()
    debug = _fixture(InformationProfile.OMNISCIENT_DEBUG)
    action = debug.state.action_affordances.actions[0]

    changed_cost = _with_actions(
        debug,
        (
            replace(
                action,
                ap_cost=replace(
                    action.ap_cost, authority=ResolutionAuthority.DEBUG_ORACLE
                ),
            ),
        ),
    )
    assert action.preview.displayed_hit_chance is not None
    changed_preview = _with_actions(
        debug,
        (
            replace(
                action,
                preview=replace(
                    action.preview,
                    displayed_hit_chance=replace(
                        action.preview.displayed_hit_chance,
                        authority=ResolutionAuthority.DEBUG_ORACLE,
                    ),
                ),
            ),
        ),
    )
    game_authority = ResolutionAuthority.GAME_PLAYER_AFFORDANCE
    changed_provenance = _with_actions(
        debug,
        (
            replace(
                action,
                provenance=AffordanceProvenance.GAME_PLAYER_AFFORDANCE,
                ap_cost=replace(action.ap_cost, authority=game_authority),
                fatigue_cost=replace(action.fatigue_cost, authority=game_authority),
                charge_cost=replace(action.charge_cost, authority=game_authority),
                ammo_cost=replace(action.ammo_cost, authority=game_authority),
                item_action_cost=replace(
                    action.item_action_cost, authority=game_authority
                ),
                preview=replace(
                    action.preview,
                    displayed_hit_chance=replace(
                        action.preview.displayed_hit_chance, authority=game_authority
                    ),
                    affected_tile_ids=replace(
                        action.preview.affected_tile_ids, authority=game_authority
                    ),
                ),
            ),
        ),
    )

    for changed in (changed_cost, changed_preview, changed_provenance):
        result = validate_fixture_pair(legal, changed)
        assert result.status is ResultStatus.VALIDATION_FAILURE
        assert result.problems[0].code is ErrorCode.FIXTURE_PAIR_MISMATCH

    assert action.debug_ground_truth is not None
    assert validate_fixture_pair(legal, debug).status is ResultStatus.SUCCESS


def test_loader_returns_structured_diagnostics_for_malformed_and_mismatched_data() -> (
    None
):
    malformed = load_fixture('{"schema_version":')
    assert malformed.problems[0].code is ErrorCode.FIXTURE_JSON_INVALID

    value = _fixture().to_dict()
    value["state_hash"] = "stale"
    stale = load_fixture(json.dumps(value))
    assert stale.problems[0].code is ErrorCode.FIXTURE_STATE_HASH_MISMATCH
    assert stale.problems[0].path == "$.state_hash"

    value = _fixture().to_dict()
    metadata = value["metadata"]
    assert isinstance(metadata, dict)
    metadata["information_profile"] = "omniscient_debug"
    mismatch = load_fixture(json.dumps(value))
    assert mismatch.problems[0].code is ErrorCode.FIXTURE_PROFILE_MISMATCH

    value = _fixture().to_dict()
    metadata = value["metadata"]
    assert isinstance(metadata, dict)
    metadata["ruleset_content_fingerprint"] = "other-catalog"
    mismatch = load_fixture(json.dumps(value))
    assert mismatch.problems[0].code is ErrorCode.FIXTURE_RULESET_MISMATCH

    value = _fixture().to_dict()
    metadata = value["metadata"]
    assert isinstance(metadata, dict)
    metadata["affordance_completeness"] = "INCOMPLETE"
    mismatch = load_fixture(json.dumps(value))
    assert mismatch.problems[0].code is ErrorCode.FIXTURE_AFFORDANCE_MISMATCH


def test_loader_rejects_duplicate_json_keys_and_unsupported_schema() -> None:
    duplicate = load_fixture('{"schema_version":"a","schema_version":"b"}')
    assert duplicate.problems[0].code is ErrorCode.FIXTURE_JSON_INVALID

    value = _fixture().to_dict()
    value["schema_version"] = "future.v99"
    unsupported = load_fixture(json.dumps(value))
    assert unsupported.problems[0].code is ErrorCode.FIXTURE_SCHEMA_UNSUPPORTED


def test_checked_in_handcrafted_fixtures_prove_preview_and_uncertainty() -> None:
    fixture_dir = Path(__file__).parent / "fixtures" / "ticket_16"
    legal = load_fixture(fixture_dir / "preview_player_legal.json")
    debug = load_fixture(fixture_dir / "preview_omniscient_debug.json")

    assert legal.status is ResultStatus.SUCCESS
    assert debug.status is ResultStatus.SUCCESS
    assert legal.value is not None and debug.value is not None
    assert (
        validate_fixture_pair(legal.value, debug.value).status is ResultStatus.SUCCESS
    )
    hostile = next(
        actor for actor in legal.value.state.combatants if actor.actor_id == "enemy"
    )
    assert hostile.resources.hit_points.value is None
    preview = legal.value.state.action_affordances.actions[0].preview
    assert preview.displayed_hit_chance is not None
    assert preview.displayed_hit_chance.value == 67
