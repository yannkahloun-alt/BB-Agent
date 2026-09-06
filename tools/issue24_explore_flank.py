from __future__ import annotations

import json
import sys
from dataclasses import fields, replace
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from bb_agent.tactical_state import ActionKind, TacticalState
from bb_agent.trace import run_decision_trace
from test_features import _formation_state
from test_mechanics import _authority, _ordinary_attack_state


def rebuild(state: TacticalState, **changes) -> TacticalState:
    values = {field.name: getattr(state, field.name) for field in fields(state)}
    values.update(state_id="")
    values.update(changes)
    return TacticalState.create(**values)


def scenario(*, hp: int, armor: int, elevation: int) -> TacticalState:
    authority = _authority()
    formation = _formation_state(
        start="flank",
        destination="screen",
        elevations={"screen": elevation},
    )
    ordinary = _ordinary_attack_state(
        authority,
        hit_points=hp,
        head_armor=armor,
        body_armor=armor,
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
    preview = attack.preview
    if preview.affected_tile_ids is not None:
        preview = replace(
            preview,
            affected_tile_ids=replace(preview.affected_tile_ids, value=["front"]),
        )
    attack = replace(attack, preview=preview)
    return rebuild(
        formation,
        combatants=tuple(actors),
        action_affordances=replace(
            formation.action_affordances,
            actions=(move, attack),
        ),
    )


def main() -> None:
    authority = _authority()
    for hp, armor, elevation in (
        (60, 0, 1),
        (60, 20, 1),
        (60, 40, 1),
        (80, 40, 1),
        (60, 0, 2),
        (60, 20, 2),
        (80, 40, 2),
    ):
        state = scenario(hp=hp, armor=armor, elevation=elevation)
        trace = run_decision_trace(authority, state)
        selection = trace.selection or {}
        records = {}
        for item in trace.evaluations:
            evaluation = item["evaluation"]
            records[item["action_id"]] = {
                "kind": item["action"]["kind"],
                "ranking_value": evaluation["ranking_value"],
                "hp_damage": evaluation["features"]["enemy_effect"]["expected_hp_damage"]["expected"],
                "kill_probability": evaluation["features"]["enemy_effect"]["kill_probability"]["expected"],
                "created_screen": evaluation["features"]["formation"]["created_direct_screen_links"]["expected"],
                "elevation_change": evaluation["features"]["position"]["elevation_change"]["expected"],
            }
        print(
            json.dumps(
                {
                    "hp": hp,
                    "armor": armor,
                    "elevation": elevation,
                    "status": trace.generation["decision_status"],
                    "chosen": selection.get("chosen_action_id"),
                    "ranking": selection.get("ranking"),
                    "records": records,
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
