from pathlib import Path

path = Path("tests/test_evaluator.py")
text = path.read_text(encoding="utf-8")

old = '''from test_mechanics import (
    _attack,
    _authority,
    _move_action,
    _movement_state,
    _ordinary_attack_state,
    _reaction,
    _snapshot,
    _wait,
)
'''
new = '''from test_mechanics import (
    _attack,
    _authority,
    _move_action,
    _movement_state,
    _ordinary_attack_state,
    _reaction,
    _snapshot,
    _wait,
)
from test_tactical_state import _unknown_resources
'''
if text.count(old) != 1:
    raise RuntimeError("import seam not found exactly once")
text = text.replace(old, new)

old = '''def _scenario_flip_state(authority, *, omniscient_hp: int | None = None):
    state = _ordinary_attack_state(authority, hit_points=10)
    brother = next(actor for actor in state.combatants if actor.actor_id == "brother")
    enemy = next(actor for actor in state.combatants if actor.actor_id == "enemy")
    if omniscient_hp is None:
        enemy_hp = KnownValue(
            Representation.SET,
            KnowledgeClass.INFERRED,
            candidates=(5, 20),
            basis=("visible-wound-band",),
        )
        information_profile = InformationProfile.PLAYER_LEGAL
    else:
        enemy_hp = KnownValue.exact(
            omniscient_hp,
            KnowledgeClass.DEBUG_GROUND_TRUTH,
        )
        information_profile = InformationProfile.OMNISCIENT_DEBUG

    enemy_one = replace(
        enemy,
        resources=replace(enemy.resources, hit_points=enemy_hp),
    )
    enemy_two = replace(
        enemy,
        actor_id="enemy-2",
        position=KnownValue.exact("northeast"),
        resources=replace(
            enemy.resources,
            hit_points=KnownValue.exact(10),
        ),
    )
'''
new = '''def _inferred_exact(value: int, basis: str) -> KnownValue:
    return KnownValue(
        Representation.EXACT,
        KnowledgeClass.INFERRED,
        value=value,
        basis=(basis,),
    )


def _scenario_flip_state(authority, *, omniscient_hp: int | None = None):
    state = _ordinary_attack_state(authority, hit_points=10)
    brother = next(actor for actor in state.combatants if actor.actor_id == "brother")
    enemy = next(actor for actor in state.combatants if actor.actor_id == "enemy")
    if omniscient_hp is None:
        enemy_hp = KnownValue(
            Representation.SET,
            KnowledgeClass.INFERRED,
            candidates=(5, 20),
            basis=("visible-wound-band",),
        )
        enemy_one_resources = replace(
            _unknown_resources(),
            hit_points=enemy_hp,
            head_armor=_inferred_exact(40, "visible-helmet"),
            body_armor=_inferred_exact(70, "visible-body-armor"),
        )
        enemy_two_resources = replace(
            _unknown_resources(),
            hit_points=_inferred_exact(10, "visible-wound-reference"),
            head_armor=_inferred_exact(40, "visible-helmet-reference"),
            body_armor=_inferred_exact(70, "visible-body-armor-reference"),
        )
        information_profile = InformationProfile.PLAYER_LEGAL
    else:
        enemy_one_resources = replace(
            enemy.resources,
            hit_points=KnownValue.exact(
                omniscient_hp,
                KnowledgeClass.DEBUG_GROUND_TRUTH,
            ),
        )
        enemy_two_resources = replace(
            enemy.resources,
            hit_points=KnownValue.exact(
                10,
                KnowledgeClass.DEBUG_GROUND_TRUTH,
            ),
        )
        information_profile = InformationProfile.OMNISCIENT_DEBUG

    enemy_one = replace(
        enemy,
        resources=enemy_one_resources,
    )
    enemy_two = replace(
        enemy,
        actor_id="enemy-2",
        position=KnownValue.exact("northeast"),
        resources=enemy_two_resources,
    )
'''
if text.count(old) != 1:
    raise RuntimeError("scenario fixture seam not found exactly once")
text = text.replace(old, new)

old = '''def test_omniscient_aleatory_aoo_spread_is_not_epistemic_uncertainty():
    authority = _authority()
    move = _move_action(reactions=(_reaction(),))
    state = _movement_state(authority, move)

    result = evaluate_decision(authority, state)
'''
new = '''def test_omniscient_aleatory_aoo_spread_is_not_epistemic_uncertainty():
    authority = _authority()
    move = _move_action(reactions=(_reaction(),))
    state = _movement_state(authority, move)
    values = {field.name: getattr(state, field.name) for field in fields(state)}
    values.update(
        state_id="",
        tiles=tuple(
            replace(
                tile,
                blocking=KnownValue.exact(False),
                traversable=KnownValue.exact(True),
                blocks_line_of_sight=KnownValue.exact(False),
            )
            for tile in state.tiles
        ),
    )
    state = TacticalState.create(**values)

    result = evaluate_decision(authority, state)
'''
if text.count(old) != 1:
    raise RuntimeError("AOO fixture seam not found exactly once")
text = text.replace(old, new)

path.write_text(text, encoding="utf-8")
print("issue #21 regression fixtures corrected")
