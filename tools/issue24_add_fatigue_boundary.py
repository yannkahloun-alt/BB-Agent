from __future__ import annotations

import sys
from dataclasses import fields, replace
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from bb_agent.fixtures import FixtureEnvelope, FixtureSeverity, load_fixture, save_fixture  # noqa: E402
from bb_agent.results import ResultStatus  # noqa: E402
from bb_agent.tactical_state import TacticalState  # noqa: E402
from bb_agent.validation import EXPECTATION_VERSION, run_validation_corpus  # noqa: E402
from test_mechanics import _authority, _wait  # noqa: E402

CORPUS = ROOT / "tests" / "fixtures" / "ticket_24"


def rebuild(state: TacticalState, **changes) -> TacticalState:
    values = {field.name: getattr(state, field.name) for field in fields(state)}
    values.update(state_id="", annotations=None)
    values.update(changes)
    return TacticalState.create(**values)


def main() -> None:
    loaded = load_fixture(CORPUS / "t24-core-attack-resolved-costs.json")
    assert loaded.status is ResultStatus.SUCCESS, loaded.problems
    assert loaded.value is not None
    source = loaded.value

    actors = []
    for actor in source.state.combatants:
        if actor.actor_id == source.state.decision.active_actor_id:
            actors.append(
                replace(
                    actor,
                    resources=replace(
                        actor.resources,
                        fatigue=replace(actor.resources.fatigue, value=95),
                    ),
                )
            )
        else:
            actors.append(actor)

    wait = _wait()
    state = rebuild(
        source.state,
        combatants=tuple(actors),
        action_affordances=replace(source.state.action_affordances, actions=(wait,)),
    )
    action = state.action_affordances.actions[0]
    metadata = replace(
        source.metadata,
        fixture_id="t24-core-fatigue-affordability-attack-excluded",
        severity=FixtureSeverity.CORE,
        taxonomy=("core_legality_affordability", "fatigue_resource_economy"),
        scenario_intent=(
            "a brother at 95/100 fatigue retains a complete current affordance set "
            "that excludes the 10-FAT Chop despite possessing the skill and weapon"
        ),
        provenance={
            "ticket": 24,
            "frozen_specs": ["#10", "#13"],
            "mechanics_source": "src/bb_agent/data/catalog.v1.json + manifest.v1.json",
            "catalog_revision": "162f498ac7c49b4c317bbf54718a595ecef6a65a",
            "evidence": (
                "#13 assigns current-command legality to the complete affordance source; "
                "the state retains Chop possession/equipment but has only 5 fatigue "
                "headroom, below the supplied current Chop fatigue cost of 10"
            ),
        },
    )
    expectations = {
        "version": EXPECTATION_VERSION,
        "expected_status": "SUCCESS",
        "exact_legal_action_ids": [action.action_id],
        "action_facts": [
            {"action_id": action.action_id, "path": "kind", "equals": "WAIT"}
        ],
    }
    fixture = FixtureEnvelope.create(
        metadata=metadata,
        state=state,
        expectations=expectations,
    )
    result = save_fixture(
        CORPUS / "t24-core-fatigue-affordability-attack-excluded.json", fixture
    )
    assert result.status is ResultStatus.SUCCESS, result.problems

    fixtures = []
    for path in sorted(CORPUS.glob("*.json")):
        current = load_fixture(path)
        assert current.status is ResultStatus.SUCCESS, current.problems
        assert current.value is not None
        fixtures.append(current.value)
    assert len(fixtures) == 33
    assert all(item.state.annotations is None for item in fixtures)
    report = run_validation_corpus(_authority(), fixtures)
    assert report.passed, report.blocking_failures
    print("validated 33 #24 fixtures including FAT affordability boundary")


if __name__ == "__main__":
    main()
