from __future__ import annotations

import sys
from dataclasses import fields, replace
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from bb_agent.evaluator import UnitValuePolicy, evaluate_decision  # noqa: E402
from bb_agent.fixtures import load_fixture  # noqa: E402
from bb_agent.results import ResultStatus  # noqa: E402
from bb_agent.tactical_state import (  # noqa: E402
    ActionKind,
    InformationProfile,
    KnowledgeClass,
    KnownValue,
    Representation,
    TacticalState,
)
from test_evaluator import _scenario_flip_state  # noqa: E402
from test_features import _formation_state  # noqa: E402
from test_mechanics import (  # noqa: E402
    _authority,
    _ordinary_attack_state,
    _resource_action,
    _snapshot,
    _wait,
)


def rebuild(state: TacticalState, **changes) -> TacticalState:
    values = {field.name: getattr(state, field.name) for field in fields(state)}
    values.update(state_id="")
    values.update(changes)
    return TacticalState.create(**values)


def show(name: str, state: TacticalState, *, policy: UnitValuePolicy | None = None) -> None:
    result = evaluate_decision(_authority(), state, unit_value_policy=policy or UnitValuePolicy())
    print("\nCASE", name, result.status)
    if result.value is None:
        print(result.problems)
        return
    print("chosen", result.value.chosen_action_id, "sensitive", result.value.information_sensitive)
    for c in result.value.candidates:
        print(c.action_id, "rank", c.ranking_value, "mean", c.mean_tactical_value, "tail", c.tail_risk.selection_penalty, "unc", c.uncertainty_span)
    print("near", result.value.near_tie_groups)
    print("scenarios", [(s.assignments, s.chosen_action_id) for s in result.value.epistemic_scenarios])


def main() -> None:
    authority = _authority()

    formation = _formation_state(start="flank", destination="screen", elevations={"screen": 1})
    move = formation.action_affordances.actions[0]
    show("protection-vs-wait", rebuild(formation, action_affordances=replace(formation.action_affordances, actions=(move, _wait()))))

    high = _snapshot(authority, _resource_action("actives.recover"), _wait())
    actors = tuple(
        replace(actor, resources=replace(actor.resources, fatigue=KnownValue.exact(80)))
        if actor.actor_id == "brother" else actor
        for actor in high.combatants
    )
    show("recover-vs-wait-fat80", rebuild(high, combatants=actors))

    show("wait-vs-end", _snapshot(authority, _wait(), _wait(ActionKind.END_TURN)))

    attack = _ordinary_attack_state(authority, hit_points=60)
    a = attack.action_affordances.actions[0]
    stable_enemy = next(x for x in attack.combatants if x.actor_id == "enemy")
    stable_enemy = replace(
        stable_enemy,
        resources=replace(
            stable_enemy.resources,
            hit_points=KnownValue(Representation.SET, KnowledgeClass.INFERRED, candidates=(40, 60), basis=("visible-wound-band",)),
            head_armor=KnownValue(Representation.SET, KnowledgeClass.INFERRED, candidates=(40, 50), basis=("visible-helmet-band",)),
            body_armor=KnownValue(Representation.SET, KnowledgeClass.INFERRED, candidates=(70, 80), basis=("visible-armor-band",)),
        ),
    )
    stable = rebuild(
        attack,
        information_profile=InformationProfile.PLAYER_LEGAL,
        raw_capture_id="t25-capture-stable",
        combatants=tuple(stable_enemy if x.actor_id == "enemy" else x for x in attack.combatants),
        action_affordances=replace(attack.action_affordances, actions=(a, _wait())),
    )
    show("stable-belief-attack-vs-wait", stable)

    flip = rebuild(_scenario_flip_state(authority), raw_capture_id="t25-capture-flip")
    show("flip-player", flip)
    for hp in (5, 20):
        show(f"flip-debug-{hp}", rebuild(_scenario_flip_state(authority, omniscient_hp=hp), raw_capture_id="t25-capture-flip"))

    preview_enemy = next(x for x in attack.combatants if x.actor_id == "enemy")
    preview_enemy = replace(
        preview_enemy,
        tactical_stats=(),
        resources=replace(
            preview_enemy.resources,
            hit_points=KnownValue(Representation.SET, KnowledgeClass.INFERRED, candidates=(40, 60), basis=("visible-wounds",)),
            head_armor=KnownValue(Representation.SET, KnowledgeClass.INFERRED, candidates=(40, 50), basis=("visible-helmet",)),
            body_armor=KnownValue(Representation.SET, KnowledgeClass.INFERRED, candidates=(70, 80), basis=("visible-armor",)),
        ),
    )
    preview = rebuild(
        attack,
        information_profile=InformationProfile.PLAYER_LEGAL,
        raw_capture_id="t25-capture-preview",
        combatants=tuple(preview_enemy if x.actor_id == "enemy" else x for x in attack.combatants),
        action_affordances=replace(attack.action_affordances, actions=(a, _wait())),
    )
    show("preview-hidden-defense", preview)

    loaded = load_fixture(ROOT / "tests" / "fixtures" / "ticket_24" / "t24-safety-high-aoo-10hp.json")
    assert loaded.status is ResultStatus.SUCCESS and loaded.value is not None
    uv = loaded.value.state
    show("unit-value-default", uv)
    show("unit-value-high", uv, policy=UnitValuePolicy(version="t25-high-value.v1", actor_values=(("brother", 4.0),)))


if __name__ == "__main__":
    main()
