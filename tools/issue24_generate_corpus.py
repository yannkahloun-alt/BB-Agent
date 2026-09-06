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
    save_fixture,
)
from bb_agent.mechanics import load_builtin_mechanics  # noqa: E402
from bb_agent.results import ResultStatus  # noqa: E402
from bb_agent.tactical_state import (  # noqa: E402
    ActionKind,
    InformationProfile,
    ItemState,
    KnownValue,
    Relation,
    TacticalState,
)
from bb_agent.validation import (  # noqa: E402
    EXPECTATION_VERSION,
    run_fixture_validation,
    run_validation_corpus,
)
from test_features import _formation_state, _known_position, _rebuild, _tiles  # noqa: E402
from test_mechanics import (  # noqa: E402
    _attack,
    _authority,
    _move_action,
    _movement_state,
    _ordinary_attack_state,
    _reaction,
    _resource_action,
    _snapshot,
    _wait,
)

OUT = ROOT / "tests" / "fixtures" / "ticket_24"


def _state_rebuild(state: TacticalState, **changes) -> TacticalState:
    values = {field.name: getattr(state, field.name) for field in fields(state)}
    values.update(state_id="")
    values.update(changes)
    return TacticalState.create(**values)


def _with_actions(state: TacticalState, *actions) -> TacticalState:
    return _state_rebuild(
        state,
        action_affordances=replace(state.action_affordances, actions=tuple(actions)),
    )


def _fixture(
    state: TacticalState,
    fixture_id: str,
    severity: FixtureSeverity,
    taxonomy: tuple[str, ...],
    intent: str,
    expectations: dict,
    evidence: str,
) -> FixtureEnvelope:
    metadata = FixtureMetadata(
        fixture_id=fixture_id,
        source_kind=FixtureSourceKind.HANDCRAFTED,
        taxonomy=taxonomy,
        severity=severity,
        scenario_intent=intent,
        ruleset_content_fingerprint=state.ruleset.content_fingerprint,
        information_profile=state.information_profile,
        affordance_completeness=state.action_affordances.completeness,
        expectation_version=EXPECTATION_VERSION,
        review_status=ReviewStatus.PROMOTED,
        provenance={
            "ticket": 24,
            "frozen_specs": ["#10", "#13"],
            "mechanics_source": "src/bb_agent/data/catalog.v1.json + manifest.v1.json",
            "catalog_revision": "162f498ac7c49b4c317bbf54718a595ecef6a65a",
            "evidence": evidence,
        },
    )
    return FixtureEnvelope.create(
        metadata=metadata,
        state=state,
        expectations=expectations,
    )


def _ids(state: TacticalState) -> list[str]:
    return [action.action_id for action in state.action_affordances.actions]


def _action_by_kind(state: TacticalState, kind: ActionKind):
    return next(action for action in state.action_affordances.actions if action.kind is kind)


def _action_by_skill(state: TacticalState, skill: str):
    return next(action for action in state.action_affordances.actions if action.skill_id == skill)


def _success(state: TacticalState, *, facts=(), extra=None) -> dict:
    payload = {
        "version": EXPECTATION_VERSION,
        "expected_status": "SUCCESS",
        "exact_legal_action_ids": _ids(state),
        "action_facts": list(facts),
    }
    if extra:
        payload.update(extra)
    return payload


def _numeric(left_action: str, path: str, op: str, right_value: float) -> dict:
    return {
        "left": {"action_id": left_action, "path": path},
        "op": op,
        "right_value": right_value,
    }


def _numeric_actions(
    left_action: str,
    left_path: str,
    op: str,
    right_action: str,
    right_path: str,
) -> dict:
    return {
        "left": {"action_id": left_action, "path": left_path},
        "op": op,
        "right": {"action_id": right_action, "path": right_path},
    }


def _ordinary_with_choice(authority, hp: int, head: int, body: int, other_kind=ActionKind.WAIT):
    base = _ordinary_attack_state(authority, hit_points=hp, head_armor=head, body_armor=body)
    attack = base.action_affordances.actions[0]
    return _with_actions(base, attack, _wait(other_kind))


def _ranged_los_state(authority, blocked: bool) -> TacticalState:
    wait = _wait()
    base = _snapshot(authority, wait)
    brother = next(actor for actor in base.combatants if actor.actor_id == "brother")
    enemy = next(actor for actor in base.combatants if actor.actor_id == "enemy")
    actors = (
        _known_position(brother, "origin"),
        _known_position(enemy, "far"),
    )
    coordinates = {"origin": (0, 0), "middle": (1, 0), "far": (2, 0)}
    return _snapshot(
        authority,
        wait,
        information_profile=InformationProfile.OMNISCIENT_DEBUG,
        combatants=actors,
        tiles=_tiles(
            coordinates,
            actors,
            los_blocks=frozenset(("middle",)) if blocked else frozenset(),
        ),
    )


def _equip_state(authority) -> TacticalState:
    base = _snapshot(authority, _wait())
    item = ItemState(
        "axe",
        KnownValue.exact("weapon.hand_axe"),
        KnownValue.exact("bag"),
        KnownValue.exact(True),
    )
    actors = tuple(
        replace(actor, equipment=(item,)) if actor.actor_id == "brother" else actor
        for actor in base.combatants
    )
    action = replace(
        _wait(),
        kind=ActionKind.EQUIP_ITEM,
        item_id="axe",
        source_location="bag",
        target_slot="mainhand",
    )
    return _snapshot(authority, action, combatants=actors)


def _safety_kill(authority, fixture_id: str, hp: int, other_kind: ActionKind) -> FixtureEnvelope:
    state = _ordinary_with_choice(authority, hp, 0, 0, other_kind)
    attack = _action_by_skill(state, "actives.chop")
    other = _action_by_kind(state, other_kind)
    expectations = _success(
        state,
        extra={
            "acceptable_top1": [attack.action_id],
            "forbidden_top1": [other.action_id],
            "required_orderings": [[attack.action_id, other.action_id]],
            "numeric_relations": [
                _numeric_actions(
                    attack.action_id,
                    "evaluation.features.enemy_effect.kill_probability.expected",
                    ">",
                    other.action_id,
                    "evaluation.features.enemy_effect.kill_probability.expected",
                )
            ],
            "required_explanations": [
                {"action_id": attack.action_id, "component_ids": ["enemy_effect"]}
            ],
        },
    )
    return _fixture(
        state,
        fixture_id,
        FixtureSeverity.SAFETY_CRITICAL,
        ("obvious_offense_kill_secure", "survival_catastrophic_risk"),
        f"secure a clearly removable adjacent threat at {hp} HP rather than give up tempo",
        expectations,
        "ordinary chop uses the pinned ordinary-attack family and resolved current preview/cost inputs",
    )


def _safety_aoo(
    authority,
    fixture_id: str,
    *,
    hp: int,
    hit: int,
    other_kind: ActionKind = ActionKind.WAIT,
    second_enemy: bool = False,
    elevation: int | None = None,
) -> FixtureEnvelope:
    reactions = (_reaction(hit_chance=hit),)
    if second_enemy:
        reactions = (_reaction("enemy", hit), _reaction("enemy-2", hit))
    move = _move_action(reactions=reactions)
    state = _movement_state(
        authority,
        move,
        mover_hp=hp,
        mover_head_armor=0,
        mover_body_armor=0,
        second_enemy=second_enemy,
    )
    if elevation is not None:
        tiles = tuple(
            replace(tile, elevation=elevation) if tile.tile_id == "east" else tile
            for tile in state.tiles
        )
        state = _state_rebuild(state, tiles=tiles)
        move = _action_by_kind(state, ActionKind.MOVE_TO)
    state = _with_actions(state, move, _wait(other_kind))
    move = _action_by_kind(state, ActionKind.MOVE_TO)
    safe = _action_by_kind(state, other_kind)
    expectations = _success(
        state,
        extra={
            "acceptable_top1": [safe.action_id],
            "forbidden_top1": [move.action_id],
            "required_orderings": [[safe.action_id, move.action_id]],
            "numeric_relations": [
                _numeric_actions(
                    move.action_id,
                    "evaluation.tail_risk.selection_penalty",
                    ">",
                    safe.action_id,
                    "evaluation.tail_risk.selection_penalty",
                ),
                _numeric(
                    move.action_id,
                    "evaluation.features.friendly_harm.movement_interruption_probability.expected",
                    ">",
                    0,
                ),
            ],
            "required_explanations": [
                {
                    "action_id": move.action_id,
                    "component_ids": ["tail_risk_penalty", "immediate_friendly_harm"],
                }
            ],
        },
    )
    tags = ["movement_path_zoc", "survival_catastrophic_risk"]
    if elevation is not None:
        tags.append("elevation_positioning")
    return _fixture(
        state,
        fixture_id,
        FixtureSeverity.SAFETY_CRITICAL,
        tuple(tags),
        "avoid a disengagement whose supplied contingent AOO creates material lethal/interruption tail risk",
        expectations,
        "#13 makes supplied contingent reactions authoritative current-command facts; ordinary AOO uses pinned chop outcome mechanics",
    )


def build() -> tuple[FixtureEnvelope, ...]:
    authority = _authority()
    fixtures: list[FixtureEnvelope] = []

    attack = _ordinary_attack_state(authority, hit_points=60, head_armor=40, body_armor=70)
    attack_action = attack.action_affordances.actions[0]
    fixtures.append(
        _fixture(
            attack,
            "t24-core-attack-resolved-costs",
            FixtureSeverity.CORE,
            ("core_legality_affordability", "obvious_offense_kill_secure"),
            "ordinary attack consumes the source-resolved AP/FAT costs exactly once",
            _success(
                attack,
                facts=(
                    {"action_id": attack_action.action_id, "path": "ap_cost.value", "equals": 4},
                    {"action_id": attack_action.action_id, "path": "fatigue_cost.value", "equals": 10},
                ),
            ),
            "pinned hand-axe/chop catalog plus #13 resolved-current-cost authority",
        )
    )

    fixtures.append(
        _fixture(
            attack,
            "t24-core-attack-armor-hp-effects",
            FixtureSeverity.CORE,
            ("obvious_offense_kill_secure",),
            "ordinary attack exposes positive HP and armor effects without collapsing branch structure",
            _success(
                attack,
                extra={
                    "numeric_relations": [
                        _numeric(attack_action.action_id, "evaluation.features.enemy_effect.expected_hp_damage.expected", ">", 0),
                        _numeric(attack_action.action_id, "evaluation.features.enemy_effect.expected_armor_damage.expected", ">", 0),
                    ],
                    "required_explanations": [
                        {"action_id": attack_action.action_id, "component_ids": ["enemy_effect"]}
                    ],
                },
            ),
            "pinned ordinary-attack independent hit/location/damage branch model",
        )
    )

    move_state = _movement_state(authority, _move_action(ap=2, fatigue=4), enemy_far=True)
    move_action = move_state.action_affordances.actions[0]
    fixtures.append(
        _fixture(
            move_state,
            "t24-core-move-resolved-path-costs",
            FixtureSeverity.CORE,
            ("core_legality_affordability", "movement_path_zoc"),
            "MOVE_TO preserves the supplied executable path and resolved AP/FAT costs",
            _success(
                move_state,
                facts=(
                    {"action_id": move_action.action_id, "path": "destination_tile_id", "equals": "east"},
                    {"action_id": move_action.action_id, "path": "ap_cost.value", "equals": 2},
                    {"action_id": move_action.action_id, "path": "fatigue_cost.value", "equals": 4},
                ),
            ),
            "#13 MOVE_TO contract: source path/cost are authoritative and are not re-pathfound by M1",
        )
    )

    elevation_state = _movement_state(authority, _move_action(), enemy_far=True)
    elevation_tiles = tuple(
        replace(tile, elevation=2) if tile.tile_id == "east" else tile
        for tile in elevation_state.tiles
    )
    elevation_state = _state_rebuild(elevation_state, tiles=elevation_tiles)
    elevation_move = elevation_state.action_affordances.actions[0]
    fixtures.append(
        _fixture(
            elevation_state,
            "t24-core-elevation-gain",
            FixtureSeverity.CORE,
            ("elevation_positioning", "movement_path_zoc"),
            "MOVE_TO records a two-level high-ground gain as a raw tactical feature",
            _success(
                elevation_state,
                extra={
                    "numeric_relations": [
                        _numeric(elevation_move.action_id, "evaluation.features.position.elevation_change.expected", "==", 2),
                        _numeric(elevation_move.action_id, "evaluation.features.position.elevation.expected", "==", 2),
                    ]
                },
            ),
            "canonical tile elevation is explicit state data; feature model compares supplied start/destination elevations",
        )
    )

    for blocked, suffix, expected in ((False, "clear", 1), (True, "blocked", 0)):
        los_state = _ranged_los_state(authority, blocked)
        wait = los_state.action_affordances.actions[0]
        fixtures.append(
            _fixture(
                los_state,
                f"t24-core-ranged-los-{suffix}",
                FixtureSeverity.CORE,
                ("los_ranged_aoe", "survival_catastrophic_risk"),
                f"known {'blocked' if blocked else 'clear'} line of sight yields deterministic ranged exposure proxy",
                _success(
                    los_state,
                    extra={
                        "numeric_relations": [
                            _numeric(wait.action_id, "evaluation.features.threat.ranged_los_exposure.expected", "==", expected)
                        ]
                    },
                ),
                "feature contract uses known LOS blocking geometry only; it does not invent enemy attack odds",
            )
        )

    wait_state = _snapshot(authority, _wait())
    wait_action = wait_state.action_affordances.actions[0]
    fixtures.append(
        _fixture(
            wait_state,
            "t24-core-wait-turn-state",
            FixtureSeverity.CORE,
            ("tempo_wait_end_turn",),
            "Wait marks the actor as having waited and unavailable to wait again",
            _success(
                wait_state,
                extra={
                    "numeric_relations": [
                        _numeric(wait_action.action_id, "evaluation.features.tempo.actor_has_waited.expected", "==", 1),
                        _numeric(wait_action.action_id, "evaluation.features.tempo.actor_may_wait.expected", "==", 0),
                    ]
                },
            ),
            "pinned deterministic Wait transition semantics",
        )
    )

    end_state = _snapshot(authority, _wait(ActionKind.END_TURN))
    end_action = end_state.action_affordances.actions[0]
    fixtures.append(
        _fixture(
            end_state,
            "t24-core-end-turn-state",
            FixtureSeverity.CORE,
            ("tempo_wait_end_turn",),
            "End Turn deterministically marks the current turn ended",
            _success(
                end_state,
                extra={"numeric_relations": [_numeric(end_action.action_id, "evaluation.features.tempo.turn_ended.expected", "==", 1)]},
            ),
            "pinned deterministic End Turn transition semantics",
        )
    )

    recover_state = _snapshot(authority, _resource_action("actives.recover"))
    recover = recover_state.action_affordances.actions[0]
    fixtures.append(
        _fixture(
            recover_state,
            "t24-core-recover-supported",
            FixtureSeverity.CORE,
            ("fatigue_resource_economy", "core_legality_affordability"),
            "Recover is a supported deterministic self/resource command with resolved AP cost",
            _success(
                recover_state,
                facts=(
                    {"action_id": recover.action_id, "path": "ap_cost.value", "equals": 9},
                    {"action_id": recover.action_id, "path": "fatigue_cost.value", "equals": 0},
                ),
            ),
            "pinned recover transition family and source-resolved current costs",
        )
    )

    reload_state = _snapshot(authority, _resource_action("actives.reload_bolt"))
    reload_action = reload_state.action_affordances.actions[0]
    fixtures.append(
        _fixture(
            reload_state,
            "t24-core-reload-supported",
            FixtureSeverity.CORE,
            ("fatigue_resource_economy", "core_legality_affordability"),
            "Reload is a supported deterministic resource transition with AP/FAT/ammo costs",
            _success(
                reload_state,
                facts=(
                    {"action_id": reload_action.action_id, "path": "ap_cost.value", "equals": 4},
                    {"action_id": reload_action.action_id, "path": "fatigue_cost.value", "equals": 20},
                    {"action_id": reload_action.action_id, "path": "ammo_cost.value", "equals": 1},
                ),
            ),
            "pinned reload_bolt resource family with crossbow/bolts prerequisites supplied by fixture helper",
        )
    )

    equip_state = _equip_state(authority)
    equip = equip_state.action_affordances.actions[0]
    fixtures.append(
        _fixture(
            equip_state,
            "t24-core-equip-supported",
            FixtureSeverity.CORE,
            ("core_legality_affordability", "fatigue_resource_economy"),
            "EQUIP_ITEM moves the declared bag item to the declared mainhand slot deterministically",
            _success(
                equip_state,
                facts=(
                    {"action_id": equip.action_id, "path": "item_id", "equals": "axe"},
                    {"action_id": equip.action_id, "path": "source_location", "equals": "bag"},
                    {"action_id": equip.action_id, "path": "target_slot", "equals": "mainhand"},
                ),
            ),
            "pinned deterministic equip transition; current command itself is supplied by complete affordance set",
        )
    )

    unsupported_state = _snapshot(authority, _wait(), _attack("mod.unknown_aoe"))
    fixtures.append(
        _fixture(
            unsupported_state,
            "t24-core-coverage-unknown-special",
            FixtureSeverity.CORE,
            ("trace_failure_coverage", "los_ranged_aoe"),
            "unknown special skill remains a legal supplied affordance but forces explicit incomplete coverage",
            {
                "version": EXPECTATION_VERSION,
                "expected_status": "INCOMPLETE_COVERAGE",
                "exact_legal_action_ids": _ids(unsupported_state),
                "expected_problem_codes": ["EVALUATION_UNSUPPORTED"],
                "expected_mechanic_ids": ["mod.unknown_aoe"],
            },
            "#13 unsupported-material-affordance rule: never drop or neutral-score unknown special content",
        )
    )

    bad_geo = _movement_state(
        authority,
        _move_action(reactions=(_reaction(),)),
        enemy_far=True,
    )
    fixtures.append(
        _fixture(
            bad_geo,
            "t24-core-coverage-impossible-aoo-geometry",
            FixtureSeverity.CORE,
            ("trace_failure_coverage", "movement_path_zoc"),
            "supplied contingent AOO with impossible reactor geometry fails coverage instead of being guessed",
            {
                "version": EXPECTATION_VERSION,
                "expected_status": "INCOMPLETE_COVERAGE",
                "exact_legal_action_ids": _ids(bad_geo),
                "expected_problem_codes": ["EVALUATION_UNSUPPORTED"],
            },
            "contingent AOO model validates supplied reactor adjacency against canonical geometry",
        )
    )

    multistep = _movement_state(
        authority,
        _move_action(
            destination="east2",
            path=("east", "east2"),
            reactions=(_reaction(),),
            ap=4,
            fatigue=8,
        ),
    )
    fixtures.append(
        _fixture(
            multistep,
            "t24-core-coverage-multistep-aoo-costs",
            FixtureSeverity.CORE,
            ("trace_failure_coverage", "movement_path_zoc"),
            "multistep AOO movement without per-step resolved costs fails closed",
            {
                "version": EXPECTATION_VERSION,
                "expected_status": "INCOMPLETE_COVERAGE",
                "exact_legal_action_ids": _ids(multistep),
                "expected_problem_codes": ["EVALUATION_UNSUPPORTED"],
            },
            "#13 no-double-application and MOVE_TO resolved-path contract require sufficient per-step cost facts",
        )
    )

    fixtures.extend(
        (
            _safety_kill(authority, "t24-safety-kill-secure-1hp", 1, ActionKind.WAIT),
            _safety_kill(authority, "t24-safety-kill-secure-5hp", 5, ActionKind.END_TURN),
            _safety_kill(authority, "t24-safety-kill-secure-10hp", 10, ActionKind.WAIT),
            _safety_kill(authority, "t24-safety-kill-secure-15hp", 15, ActionKind.END_TURN),
            _safety_aoo(authority, "t24-safety-lethal-aoo-1hp", hp=1, hit=95),
            _safety_aoo(authority, "t24-safety-lethal-aoo-5hp", hp=5, hit=95, other_kind=ActionKind.END_TURN),
            _safety_aoo(authority, "t24-safety-high-aoo-10hp", hp=10, hit=85),
            _safety_aoo(authority, "t24-safety-double-aoo-20hp", hp=20, hit=67, second_enemy=True),
            _safety_aoo(authority, "t24-safety-uphill-aoo-trap", hp=10, hit=85, elevation=2),
        )
    )

    formation_state = _formation_state(start="screen", destination="flank")
    move = formation_state.action_affordances.actions[0]
    formation_state = _with_actions(formation_state, move, _wait())
    move = _action_by_kind(formation_state, ActionKind.MOVE_TO)
    wait = _action_by_kind(formation_state, ActionKind.WAIT)
    fixtures.append(
        _fixture(
            formation_state,
            "t24-safety-vacate-screen",
            FixtureSeverity.SAFETY_CRITICAL,
            ("protection_formation", "survival_catastrophic_risk", "movement_path_zoc"),
            "do not vacate the direct screen protecting a 10-HP ally when a safe hold is available",
            _success(
                formation_state,
                extra={
                    "acceptable_top1": [wait.action_id],
                    "forbidden_top1": [move.action_id],
                    "required_orderings": [[wait.action_id, move.action_id]],
                    "numeric_relations": [
                        _numeric(move.action_id, "evaluation.features.formation.lost_direct_screen_links.expected", ">", 0),
                        _numeric(wait.action_id, "evaluation.features.formation.lost_direct_screen_links.expected", "==", 0),
                    ],
                    "required_explanations": [
                        {"action_id": move.action_id, "component_ids": ["position_control_protection"]}
                    ],
                },
            ),
            "formation feature contract treats loss of direct screen link as explicit raw fact; vulnerable ally HP is canonical state",
        )
    )

    assert len(fixtures) == 24
    assert sum(f.metadata.severity is FixtureSeverity.SAFETY_CRITICAL for f in fixtures) == 10
    assert all(f.metadata.review_status is ReviewStatus.PROMOTED for f in fixtures)

    for fixture in fixtures:
        report = run_fixture_validation(authority, fixture)
        if not report.passed:
            raise AssertionError(
                f"{fixture.metadata.fixture_id} failed: "
                + "; ".join(item.message for item in report.blocking_failures)
            )

    corpus = run_validation_corpus(authority, fixtures)
    if not corpus.passed:
        raise AssertionError(corpus.blocking_failures)
    return tuple(fixtures)


def main() -> None:
    result = load_builtin_mechanics()
    assert result.status is ResultStatus.SUCCESS
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    fixtures = build()
    for fixture in fixtures:
        result = save_fixture(OUT / f"{fixture.metadata.fixture_id}.json", fixture)
        assert result.status is ResultStatus.SUCCESS, result.problems
    print(f"generated {len(fixtures)} ticket #24 fixtures")


if __name__ == "__main__":
    main()
