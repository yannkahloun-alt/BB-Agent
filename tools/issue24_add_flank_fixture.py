from __future__ import annotations

import sys
from dataclasses import fields, replace
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from bb_agent.fixtures import (  # noqa: E402
    FixtureEnvelope,
    FixtureMetadata,
    FixtureSeverity,
    FixtureSourceKind,
    ReviewStatus,
    load_fixture,
    save_fixture,
)
from bb_agent.results import ResultStatus  # noqa: E402
from bb_agent.tactical_state import ActionKind, TacticalState  # noqa: E402
from bb_agent.validation import EXPECTATION_VERSION, run_validation_corpus  # noqa: E402
from test_features import _formation_state  # noqa: E402
from test_mechanics import _authority, _ordinary_attack_state  # noqa: E402

CORPUS = ROOT / "tests" / "fixtures" / "ticket_24"


def rebuild(state: TacticalState, **changes) -> TacticalState:
    values = {field.name: getattr(state, field.name) for field in fields(state)}
    values.update(state_id="")
    values.update(changes)
    return TacticalState.create(**values)


def build_fixture() -> FixtureEnvelope:
    authority = _authority()
    formation = _formation_state(
        start="flank",
        destination="screen",
        elevations={"screen": 2},
    )
    ordinary = _ordinary_attack_state(
        authority,
        hit_points=60,
        head_armor=0,
        body_armor=0,
    )
    ordinary_brother = next(
        actor for actor in ordinary.combatants if actor.actor_id == "brother"
    )
    ordinary_enemy = next(
        actor for actor in ordinary.combatants if actor.actor_id == "enemy"
    )
    actors = []
    for actor in formation.combatants:
        if actor.actor_id == "brother":
            actors.append(
                replace(
                    actor,
                    skills=ordinary_brother.skills,
                    equipment=ordinary_brother.equipment,
                    perks=ordinary_brother.perks,
                    traits=ordinary_brother.traits,
                )
            )
        elif actor.actor_id == "enemy":
            actors.append(
                replace(
                    actor,
                    resources=ordinary_enemy.resources,
                    perks=ordinary_enemy.perks,
                    traits=ordinary_enemy.traits,
                )
            )
        else:
            actors.append(actor)

    move = formation.action_affordances.actions[0]
    attack = ordinary.action_affordances.actions[0]
    if attack.preview.affected_tile_ids is not None:
        attack = replace(
            attack,
            preview=replace(
                attack.preview,
                affected_tile_ids=replace(
                    attack.preview.affected_tile_ids,
                    value=["front"],
                ),
            ),
        )
    state = rebuild(
        formation,
        combatants=tuple(actors),
        action_affordances=replace(
            formation.action_affordances,
            actions=(move, attack),
        ),
    )
    move = next(
        action for action in state.action_affordances.actions
        if action.kind is ActionKind.MOVE_TO
    )
    attack = next(
        action for action in state.action_affordances.actions
        if action.kind is ActionKind.USE_SKILL
    )
    expectations = {
        "version": EXPECTATION_VERSION,
        "expected_status": "SUCCESS",
        "exact_legal_action_ids": [move.action_id, attack.action_id],
        "acceptable_top1": [move.action_id],
        "forbidden_top1": [attack.action_id],
        "required_orderings": [[move.action_id, attack.action_id]],
        "numeric_relations": [
            {
                "left": {
                    "action_id": attack.action_id,
                    "path": "evaluation.features.enemy_effect.expected_hp_damage.expected",
                },
                "op": ">",
                "right_value": 20,
            },
            {
                "left": {
                    "action_id": move.action_id,
                    "path": "evaluation.features.formation.created_direct_screen_links.expected",
                },
                "op": ">",
                "right_value": 0,
            },
            {
                "left": {
                    "action_id": move.action_id,
                    "path": "evaluation.features.position.elevation_change.expected",
                },
                "op": "==",
                "right_value": 2,
            },
            {
                "left": {
                    "action_id": attack.action_id,
                    "path": "evaluation.features.formation.created_direct_screen_links.expected",
                },
                "op": "==",
                "right_value": 0,
            },
        ],
        "required_explanations": [
            {
                "action_id": move.action_id,
                "component_ids": ["position_control_ally_protection"],
            },
            {
                "action_id": attack.action_id,
                "component_ids": ["enemy_effect"],
            },
        ],
    }
    metadata = FixtureMetadata(
        fixture_id="t24-safety-high-damage-vs-protect-flank",
        source_kind=FixtureSourceKind.HANDCRAFTED,
        taxonomy=(
            "obvious_offense_kill_secure",
            "protection_formation",
            "elevation_positioning",
            "survival_catastrophic_risk",
        ),
        severity=FixtureSeverity.SAFETY_CRITICAL,
        scenario_intent=(
            "prefer immediately screening a vulnerable 10-HP ally over a materially "
            "damaging ordinary attack that leaves the flank exposed"
        ),
        ruleset_content_fingerprint=state.ruleset.content_fingerprint,
        information_profile=state.information_profile,
        affordance_completeness=state.action_affordances.completeness,
        expectation_version=EXPECTATION_VERSION,
        review_status=ReviewStatus.PROMOTED,
        provenance={
            "ticket": 24,
            "frozen_specs": ["#10", "#13"],
            "mechanics_source": (
                "src/bb_agent/data/catalog.v1.json + manifest.v1.json"
            ),
            "catalog_revision": "162f498ac7c49b4c317bbf54718a595ecef6a65a",
            "evidence": (
                "ordinary chop uses the pinned ordinary-attack source subset; "
                "screen/elevation consequences use canonical current-state geometry. "
                "M1 has no movement-coupled attack family, so this fixture encodes the "
                "same current-decision safety tradeoff as attack-now versus screen-now, "
                "without inventing an unsupported charge/attack transition."
            ),
        },
    )
    return FixtureEnvelope.create(
        metadata=metadata,
        state=state,
        expectations=expectations,
    )


def main() -> None:
    fixture = build_fixture()
    result = save_fixture(
        CORPUS / "t24-safety-high-damage-vs-protect-flank.json",
        fixture,
    )
    assert result.status is ResultStatus.SUCCESS, result.problems

    fixtures = []
    for path in sorted(CORPUS.glob("*.json")):
        loaded = load_fixture(path)
        assert loaded.status is ResultStatus.SUCCESS, loaded.problems
        assert loaded.value is not None
        fixtures.append(loaded.value)
    assert len(fixtures) == 25
    assert sum(
        item.metadata.severity is FixtureSeverity.SAFETY_CRITICAL
        for item in fixtures
    ) == 11
    report = run_validation_corpus(_authority(), fixtures)
    assert report.passed, report.blocking_failures
    print("validated 25 ticket #24 fixtures with 11 SAFETY_CRITICAL")


if __name__ == "__main__":
    main()
