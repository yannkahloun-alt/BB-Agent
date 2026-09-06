from __future__ import annotations

import sys
from dataclasses import fields, replace
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from bb_agent.fixtures import (  # noqa: E402
    FixtureEnvelope,
    FixtureSeverity,
    load_fixture,
    save_fixture,
)
from bb_agent.results import ResultStatus  # noqa: E402
from bb_agent.tactical_state import ActionKind, KnownValue, TacticalState  # noqa: E402
from bb_agent.validation import EXPECTATION_VERSION, run_validation_corpus  # noqa: E402
from test_mechanics import (  # noqa: E402
    _authority,
    _move_action,
    _movement_state,
    _wait,
)

CORPUS = ROOT / "tests" / "fixtures" / "ticket_24"
REVISION = "162f498ac7c49b4c317bbf54718a595ecef6a65a"
KILL_FIXTURES = (
    "t24-safety-kill-secure-1hp",
    "t24-safety-kill-secure-5hp",
    "t24-safety-kill-secure-10hp",
    "t24-safety-kill-secure-15hp",
)


def load(name: str) -> FixtureEnvelope:
    result = load_fixture(CORPUS / f"{name}.json")
    assert result.status is ResultStatus.SUCCESS, result.problems
    assert result.value is not None
    return result.value


def save(fixture: FixtureEnvelope) -> None:
    result = save_fixture(CORPUS / f"{fixture.metadata.fixture_id}.json", fixture)
    assert result.status is ResultStatus.SUCCESS, result.problems


def rebuild(state: TacticalState, **changes) -> TacticalState:
    values = {field.name: getattr(state, field.name) for field in fields(state)}
    values.update(state_id="", annotations=None)
    values.update(changes)
    return TacticalState.create(**values)


def provenance(evidence: str) -> dict[str, object]:
    return {
        "ticket": 24,
        "frozen_specs": ["#10", "#13"],
        "mechanics_source": "src/bb_agent/data/catalog.v1.json + manifest.v1.json",
        "catalog_revision": REVISION,
        "evidence": evidence,
    }


def metadata_from(
    base: FixtureEnvelope,
    *,
    fixture_id: str,
    severity: FixtureSeverity,
    taxonomy: tuple[str, ...],
    intent: str,
    evidence: str,
):
    return replace(
        base.metadata,
        fixture_id=fixture_id,
        severity=severity,
        taxonomy=taxonomy,
        scenario_intent=intent,
        provenance=provenance(evidence),
    )


def success_exact(state: TacticalState, *, facts=()) -> dict[str, object]:
    return {
        "version": EXPECTATION_VERSION,
        "expected_status": "SUCCESS",
        "exact_legal_action_ids": [
            action.action_id for action in state.action_affordances.actions
        ],
        "action_facts": list(facts),
    }


def downgrade_kill_secure() -> None:
    for fixture_id in KILL_FIXTURES:
        fixture = load(fixture_id)
        metadata = replace(
            fixture.metadata,
            severity=FixtureSeverity.CORE,
            taxonomy=("obvious_offense_kill_secure",),
            provenance=provenance(
                "ordinary chop kill-secure ranking against Wait/End Turn; this is a "
                "CORE offense/tempo assertion, not a catastrophic-risk fixture"
            ),
        )
        save(
            FixtureEnvelope.create(
                metadata=metadata,
                state=replace(fixture.state, annotations=None).normalized(),
                expectations=fixture.expectations,
                oracle_annotations=fixture.oracle_annotations,
            )
        )


def update_high_damage_flank() -> None:
    fixture = load("t24-safety-high-damage-vs-protect-flank")
    actors = []
    for actor in fixture.state.combatants:
        if actor.actor_id == fixture.state.decision.active_actor_id:
            actors.append(
                replace(
                    actor,
                    resources=replace(
                        actor.resources,
                        action_points=replace(actor.resources.action_points, value=4),
                    ),
                )
            )
        else:
            actors.append(actor)
    state = rebuild(fixture.state, combatants=tuple(actors))
    move = next(
        action
        for action in state.action_affordances.actions
        if action.kind is ActionKind.MOVE_TO
    )
    attack = next(
        action
        for action in state.action_affordances.actions
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
                    "path": "evaluation.features.resources.remaining_action_points.expected",
                },
                "op": "==",
                "right_value": 0,
            },
            {
                "left": {
                    "action_id": move.action_id,
                    "path": "evaluation.features.resources.remaining_action_points.expected",
                },
                "op": "==",
                "right_value": 2,
            },
        ],
        "required_explanations": [
            {
                "action_id": move.action_id,
                "component_ids": ["position_control_ally_protection"],
            },
            {"action_id": attack.action_id, "component_ids": ["enemy_effect"]},
        ],
    }
    metadata = replace(
        fixture.metadata,
        scenario_intent=(
            "with exactly 4 AP remaining, prefer immediately screening a vulnerable "
            "10-HP ally over a materially damaging 4-AP Chop that consumes the rest "
            "of the actor's turn and leaves the flank exposed"
        ),
        provenance=provenance(
            "ordinary Chop uses the pinned attack model and costs all 4 current AP; "
            "the competing 2-AP MOVE_TO creates the canonical screen and gains two "
            "elevation levels, making damage-now and protection-now mutually exclusive "
            "within the current decision without inventing a movement-coupled attack"
        ),
    )
    save(FixtureEnvelope.create(metadata=metadata, state=state, expectations=expectations))


def add_screen_variant(source_id: str, fixture_id: str, ally_hp: int) -> None:
    source = load(source_id)
    actors = []
    for actor in source.state.combatants:
        if actor.actor_id == "ally":
            actors.append(
                replace(
                    actor,
                    resources=replace(
                        actor.resources,
                        hit_points=replace(actor.resources.hit_points, value=ally_hp),
                    ),
                )
            )
        else:
            actors.append(actor)
    state = rebuild(source.state, combatants=tuple(actors))
    metadata = metadata_from(
        source,
        fixture_id=fixture_id,
        severity=FixtureSeverity.SAFETY_CRITICAL,
        taxonomy=(
            "movement_path_zoc",
            "protection_formation",
            "survival_catastrophic_risk",
        ),
        intent=(
            f"do not vacate the direct screen protecting a critically vulnerable "
            f"{ally_hp}-HP ally when a safe hold is available"
        ),
        evidence=(
            "canonical formation features expose the lost direct screen link; the "
            f"protected ally is at {ally_hp} HP, so voluntarily abandoning the screen "
            "is an explicit catastrophic protection failure"
        ),
    )
    save(
        FixtureEnvelope.create(
            metadata=metadata,
            state=state,
            expectations=source.expectations,
        )
    )


def add_low_probability_lethal_aoo() -> None:
    source = load("t24-safety-lethal-aoo-1hp")
    actions = []
    for action in source.state.action_affordances.actions:
        if action.kind is ActionKind.MOVE_TO:
            reactions = tuple(
                replace(
                    reaction,
                    hit_chance=replace(reaction.hit_chance, value=33),
                )
                for reaction in action.contingent_reactions
            )
            actions.append(replace(action, contingent_reactions=reactions))
        else:
            actions.append(action)
    state = rebuild(
        source.state,
        action_affordances=replace(
            source.state.action_affordances,
            actions=tuple(actions),
        ),
    )
    move = next(
        action
        for action in state.action_affordances.actions
        if action.kind is ActionKind.MOVE_TO
    )
    safe = next(
        action
        for action in state.action_affordances.actions
        if action.kind is not ActionKind.MOVE_TO
    )
    expectations = {
        "version": EXPECTATION_VERSION,
        "expected_status": "SUCCESS",
        "exact_legal_action_ids": [safe.action_id, move.action_id],
        "acceptable_top1": [safe.action_id],
        "forbidden_top1": [move.action_id],
        "required_orderings": [[safe.action_id, move.action_id]],
        "numeric_relations": [
            {
                "left": {
                    "action_id": move.action_id,
                    "path": "evaluation.tail_risk.selection_penalty",
                },
                "op": ">",
                "right": {
                    "action_id": safe.action_id,
                    "path": "evaluation.tail_risk.selection_penalty",
                },
            },
            {
                "left": {
                    "action_id": move.action_id,
                    "path": "evaluation.features.friendly_harm.self_death_probability.expected",
                },
                "op": ">",
                "right_value": 0,
            },
        ],
        "required_explanations": [
            {
                "action_id": move.action_id,
                "component_ids": ["tail_risk_penalty", "immediate_friendly_harm"],
            }
        ],
    }
    metadata = metadata_from(
        source,
        fixture_id="t24-safety-low-probability-lethal-aoo",
        severity=FixtureSeverity.SAFETY_CRITICAL,
        taxonomy=("movement_path_zoc", "survival_catastrophic_risk"),
        intent=(
            "avoid a 33%-hit disengagement AOO when the 1-HP active brother dies on "
            "any landed reaction and a safe hold exists"
        ),
        evidence=(
            "#13 supplied contingent AOO is authoritative; the 1-HP actor makes even "
            "a lower-probability landed Chop a catastrophic death-tail event"
        ),
    )
    save(FixtureEnvelope.create(metadata=metadata, state=state, expectations=expectations))


def add_affordability_fixture() -> None:
    source = load("t24-core-attack-resolved-costs")
    wait = _wait()
    actors = []
    for actor in source.state.combatants:
        if actor.actor_id == source.state.decision.active_actor_id:
            actors.append(
                replace(
                    actor,
                    resources=replace(
                        actor.resources,
                        action_points=replace(actor.resources.action_points, value=3),
                    ),
                )
            )
        else:
            actors.append(actor)
    state = rebuild(
        source.state,
        combatants=tuple(actors),
        action_affordances=replace(
            source.state.action_affordances,
            actions=(wait,),
        ),
    )
    metadata = metadata_from(
        source,
        fixture_id="t24-core-affordability-attack-excluded",
        severity=FixtureSeverity.CORE,
        taxonomy=("core_legality_affordability",),
        intent=(
            "a brother with only 3 AP retains a complete current affordance set that "
            "does not contain the 4-AP Chop despite possessing the skill and weapon"
        ),
        evidence=(
            "#13 assigns current-command legality to the complete affordance source; "
            "the state retains Chop possession/equipment but only 3 AP, while the "
            "known Chop resolved AP cost is 4"
        ),
    )
    save(
        FixtureEnvelope.create(
            metadata=metadata,
            state=state,
            expectations=success_exact(
                state,
                facts=(
                    {
                        "action_id": state.action_affordances.actions[0].action_id,
                        "path": "kind",
                        "equals": "WAIT",
                    },
                ),
            ),
        )
    )


def add_range_fixture() -> None:
    source = load("t24-core-ranged-los-clear")
    state = replace(source.state, annotations=None).normalized()
    metadata = metadata_from(
        source,
        fixture_id="t24-core-range-attack-excluded",
        severity=FixtureSeverity.CORE,
        taxonomy=("core_legality_affordability", "los_ranged_aoe"),
        intent=(
            "a complete current affordance set omits an ordinary melee attack when "
            "the visible hostile is more than one canonical hex away"
        ),
        evidence=(
            "#13 makes the supplied complete current affordance set authoritative; "
            "canonical hex geometry places the visible hostile outside adjacent melee "
            "range and the fixture exposes only the executable Wait command"
        ),
    )
    save(
        FixtureEnvelope.create(
            metadata=metadata,
            state=state,
            expectations=success_exact(state),
        )
    )


def add_target_fixture() -> None:
    source = load("t24-core-attack-resolved-costs")
    state = replace(source.state, annotations=None).normalized()
    action = state.action_affordances.actions[0]
    metadata = metadata_from(
        source,
        fixture_id="t24-core-target-affordance-integrity",
        severity=FixtureSeverity.CORE,
        taxonomy=("core_legality_affordability", "obvious_offense_kill_secure"),
        intent=(
            "ordinary attack affordance preserves the exact executable actor target and "
            "affected current tile supplied by the complete affordance source"
        ),
        evidence=(
            "#13 targetability is source-authoritative; this fixture pins target actor, "
            "target kind and player-visible affected tile without reconstructing "
            "Battle Brothers target legality"
        ),
    )
    save(
        FixtureEnvelope.create(
            metadata=metadata,
            state=state,
            expectations=success_exact(
                state,
                facts=(
                    {
                        "action_id": action.action_id,
                        "path": "target_actor_id",
                        "equals": "enemy",
                    },
                    {
                        "action_id": action.action_id,
                        "path": "target_kind",
                        "equals": "ACTOR",
                    },
                    {
                        "action_id": action.action_id,
                        "path": "preview.affected_tile_ids.value",
                        "equals": ["east"],
                    },
                ),
            ),
        )
    )


def add_terrain_fixture() -> None:
    authority = _authority()
    state = _movement_state(
        authority,
        _move_action(ap=4, fatigue=8),
        enemy_far=True,
    )
    tiles = tuple(
        replace(tile, terrain=KnownValue.exact("swamp"))
        if tile.tile_id == "east"
        else tile
        for tile in state.tiles
    )
    state = rebuild(state, tiles=tiles)
    action = state.action_affordances.actions[0]
    source = load("t24-core-move-resolved-path-costs")
    metadata = metadata_from(
        source,
        fixture_id="t24-core-terrain-resolved-move-cost",
        severity=FixtureSeverity.CORE,
        taxonomy=(
            "core_legality_affordability",
            "movement_path_zoc",
            "elevation_positioning",
        ),
        intent=(
            "movement into known swamp terrain preserves the source-resolved executable "
            "path and its current 4-AP/8-FAT cost without BB-Agent re-pathfinding"
        ),
        evidence=(
            "#13 assigns current terrain-adjusted path/cost authority to the MOVE_TO "
            "affordance; the destination terrain is canonical state while 4 AP / 8 FAT "
            "are explicit resolved current-command costs"
        ),
    )
    save(
        FixtureEnvelope.create(
            metadata=metadata,
            state=state,
            expectations=success_exact(
                state,
                facts=(
                    {
                        "action_id": action.action_id,
                        "path": "destination_tile_id",
                        "equals": "east",
                    },
                    {
                        "action_id": action.action_id,
                        "path": "ap_cost.value",
                        "equals": 4,
                    },
                    {
                        "action_id": action.action_id,
                        "path": "fatigue_cost.value",
                        "equals": 8,
                    },
                ),
            ),
        )
    )


def main() -> None:
    downgrade_kill_secure()
    update_high_damage_flank()
    add_screen_variant(
        "t24-safety-vacate-screen",
        "t24-safety-vacate-screen-1hp",
        1,
    )
    add_screen_variant(
        "t24-safety-vacate-screen",
        "t24-safety-vacate-screen-5hp",
        5,
    )
    add_low_probability_lethal_aoo()
    add_affordability_fixture()
    add_range_fixture()
    add_target_fixture()
    add_terrain_fixture()

    fixtures = []
    for path in sorted(CORPUS.glob("*.json")):
        loaded = load_fixture(path)
        assert loaded.status is ResultStatus.SUCCESS, loaded.problems
        assert loaded.value is not None
        fixtures.append(loaded.value)
    assert len(fixtures) == 32
    assert sum(
        fixture.metadata.severity is FixtureSeverity.SAFETY_CRITICAL
        for fixture in fixtures
    ) == 10
    assert all(fixture.state.annotations is None for fixture in fixtures)
    report = run_validation_corpus(_authority(), fixtures)
    assert report.passed, report.blocking_failures
    print("validated 32 #24 fixtures with 10 genuine SAFETY_CRITICAL cases")


if __name__ == "__main__":
    main()
