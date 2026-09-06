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
from bb_agent.tactical_state import (  # noqa: E402
    ActionKind,
    InformationProfile,
    KnowledgeClass,
    KnownValue,
    Relation,
    Representation,
    TacticalState,
)
from bb_agent.validation import EXPECTATION_VERSION, run_validation_corpus  # noqa: E402
from test_evaluator import _scenario_flip_state  # noqa: E402
from test_features import _formation_state, _known_position, _tiles  # noqa: E402
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

CORPUS = ROOT / "tests" / "fixtures" / "ticket_25"
CORE_SAFETY = ROOT / "tests" / "fixtures" / "ticket_24"
FROZEN = ["#2", "#5", "#6", "#10", "#13"]
CATALOG_REVISION = "162f498ac7c49b4c317bbf54718a595ecef6a65a"


def rebuild(state: TacticalState, **changes) -> TacticalState:
    values = {field.name: getattr(state, field.name) for field in fields(state)}
    values.update(state_id="", annotations=None)
    values.update(changes)
    return TacticalState.create(**values)


def actions(state: TacticalState):
    return state.action_affordances.actions


def by_kind(state: TacticalState, kind: ActionKind):
    return next(action for action in actions(state) if action.kind is kind)


def by_skill(state: TacticalState, skill_id: str):
    return next(action for action in actions(state) if action.skill_id == skill_id)


def by_target(state: TacticalState, actor_id: str):
    return next(action for action in actions(state) if action.target_actor_id == actor_id)


def wait_action(state: TacticalState):
    return by_kind(state, ActionKind.WAIT)


def metadata(
    fixture_id: str,
    state: TacticalState,
    taxonomy: tuple[str, ...],
    intent: str,
    evidence: str,
    *,
    severity: FixtureSeverity = FixtureSeverity.QUALITY,
) -> FixtureMetadata:
    return FixtureMetadata(
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
            "ticket": 25,
            "frozen_specs": FROZEN,
            "mechanics_source": "src/bb_agent/data/catalog.v1.json + manifest.v1.json",
            "catalog_revision": CATALOG_REVISION,
            "evidence": evidence,
        },
    )


def fixture(
    fixture_id: str,
    state: TacticalState,
    taxonomy: tuple[str, ...],
    intent: str,
    evidence: str,
    expectations: dict,
    *,
    severity: FixtureSeverity = FixtureSeverity.QUALITY,
) -> FixtureEnvelope:
    return FixtureEnvelope.create(
        metadata=metadata(
            fixture_id,
            state,
            taxonomy,
            intent,
            evidence,
            severity=severity,
        ),
        state=state,
        expectations={"version": EXPECTATION_VERSION, **expectations},
    )


def relation(action_id: str, path: str, op: str, *, right_id=None, right_path=None, value=None):
    item = {"left": {"action_id": action_id, "path": path}, "op": op}
    if right_id is not None:
        item["right"] = {"action_id": right_id, "path": right_path}
    else:
        item["right_value"] = value
    return item


def exact_ids(state: TacticalState) -> list[str]:
    return sorted(action.action_id for action in actions(state))


def add_wait(state: TacticalState) -> TacticalState:
    current = actions(state)
    if any(action.kind is ActionKind.WAIT for action in current):
        return state
    return rebuild(
        state,
        action_affordances=replace(
            state.action_affordances,
            actions=tuple(current) + (_wait(),),
        ),
    )


def quality_zero_damage_protect() -> FixtureEnvelope:
    state = add_wait(
        _formation_state(start="flank", destination="screen", elevations={"screen": 1})
    )
    move = by_kind(state, ActionKind.MOVE_TO)
    wait = wait_action(state)
    return fixture(
        "t25-quality-zero-damage-protect",
        state,
        ("protection_formation", "elevation_positioning"),
        "prefer a zero-damage reposition that immediately creates a direct screen for a vulnerable ally",
        "#5 requires position and ally protection to carry independent value; the canonical geometry creates one screen link and one elevation level without inventing damage",
        {
            "expected_status": "SUCCESS",
            "exact_legal_action_ids": exact_ids(state),
            "acceptable_top1": [move.action_id],
            "forbidden_top1": [wait.action_id],
            "required_orderings": [[move.action_id, wait.action_id]],
            "numeric_relations": [
                relation(move.action_id, "evaluation.features.enemy_effect.expected_hp_damage.expected", "==", value=0),
                relation(move.action_id, "evaluation.features.formation.created_direct_screen_links.expected", "==", value=1),
                relation(move.action_id, "evaluation.features.position.elevation_change.expected", "==", value=1),
            ],
            "required_explanations": [
                {"action_id": move.action_id, "component_ids": ["position_control_ally_protection"]}
            ],
        },
    )


def quality_high_ground() -> FixtureEnvelope:
    state = add_wait(
        _formation_state(start="flank", destination="screen", elevations={"screen": 2})
    )
    move = by_kind(state, ActionKind.MOVE_TO)
    return fixture(
        "t25-quality-high-ground-position",
        state,
        ("elevation_positioning", "protection_formation"),
        "make the supported high-ground positional gain visible as a first-class tactical component",
        "#5 requires elevation and position/control to remain inspectable; the supplied MOVE_TO gains two canonical elevation levels",
        {
            "expected_status": "SUCCESS",
            "exact_legal_action_ids": exact_ids(state),
            "numeric_relations": [
                relation(move.action_id, "evaluation.features.position.elevation_change.expected", "==", value=2),
                relation(move.action_id, "evaluation.features.position.elevation_advantage_contacts.minimum", ">", value=0),
            ],
            "required_explanations": [
                {"action_id": move.action_id, "component_ids": ["position_control_ally_protection"]}
            ],
        },
    )


def quality_surround_control() -> FixtureEnvelope:
    authority = _authority()
    base = _snapshot(authority, _move_action())
    brother = next(actor for actor in base.combatants if actor.actor_id == "brother")
    enemy = next(actor for actor in base.combatants if actor.actor_id == "enemy")
    ally = replace(
        brother,
        actor_id="ally",
        relation=Relation.PLAYER,
        is_player_controlled=False,
    )
    enemy2 = replace(enemy, actor_id="enemy-2")
    combatants = (
        _known_position(brother, "start"),
        _known_position(ally, "ally"),
        _known_position(enemy, "enemy-1"),
        _known_position(enemy2, "enemy-2"),
    )
    coordinates = {
        "center": (0, 0),
        "start": (-1, 1),
        "ally": (1, -1),
        "enemy-1": (1, 0),
        "enemy-2": (0, 1),
    }
    move = _move_action(destination="center", path=("center",))
    state = _snapshot(
        authority,
        move,
        _wait(),
        information_profile=InformationProfile.OMNISCIENT_DEBUG,
        combatants=combatants,
        tiles=_tiles(coordinates, combatants),
    )
    state = rebuild(state)
    move = by_kind(state, ActionKind.MOVE_TO)
    return fixture(
        "t25-quality-surround-control",
        state,
        ("control_disable_threat_priority", "elevation_positioning"),
        "represent a zero-damage move that creates supported surround/flank control rather than valuing only immediate damage",
        "#5 requires surround/control to be a raw feature; the canonical center move creates at least one flanked hostile in the supplied geometry",
        {
            "expected_status": "SUCCESS",
            "exact_legal_action_ids": exact_ids(state),
            "numeric_relations": [
                relation(move.action_id, "evaluation.features.control.flanked_hostiles.minimum", ">", value=0),
                relation(move.action_id, "evaluation.features.enemy_effect.expected_hp_damage.expected", "==", value=0),
            ],
            "required_explanations": [
                {"action_id": move.action_id, "component_ids": ["position_control_ally_protection"]}
            ],
        },
    )


def quality_escape_flexibility() -> FixtureEnvelope:
    authority = _authority()
    base = _snapshot(authority, _move_action())
    brother = next(actor for actor in base.combatants if actor.actor_id == "brother")
    enemy = next(actor for actor in base.combatants if actor.actor_id == "enemy")
    combatants = (
        _known_position(brother, "start"),
        _known_position(enemy, "far"),
    )
    coordinates = {
        "start": (-1, 0),
        "open": (0, 0),
        "east": (1, 0),
        "northeast": (1, -1),
        "northwest": (0, -1),
        "southwest": (-1, 1),
        "southeast": (0, 1),
        "far": (3, 0),
    }
    move = _move_action(destination="open", path=("open",))
    state = _snapshot(
        authority,
        move,
        _wait(),
        information_profile=InformationProfile.OMNISCIENT_DEBUG,
        combatants=combatants,
        tiles=_tiles(coordinates, combatants, elevations={"open": 1}),
    )
    state = rebuild(state)
    move = by_kind(state, ActionKind.MOVE_TO)
    wait = wait_action(state)
    return fixture(
        "t25-quality-escape-flexibility",
        state,
        ("elevation_positioning", "movement_path_zoc"),
        "preserve tactical flexibility by moving into an open tile with more future reposition options",
        "#5 requires escape/reposition options and future-action potential to remain explicit; the supplied adjacent MOVE_TO enters the center of a six-neighbor open cluster",
        {
            "expected_status": "SUCCESS",
            "exact_legal_action_ids": exact_ids(state),
            "numeric_relations": [
                relation(
                    move.action_id,
                    "evaluation.features.mobility.open_adjacent_reposition_tiles.expected",
                    ">",
                    right_id=wait.action_id,
                    right_path="evaluation.features.mobility.open_adjacent_reposition_tiles.expected",
                ),
                relation(move.action_id, "evaluation.features.position.elevation_change.expected", "==", value=1),
            ],
        },
    )


def quality_fatigue_sustainable() -> FixtureEnvelope:
    authority = _authority()
    reload_action = _resource_action("actives.reload_bolt")
    move = _move_action(destination="east", path=("east",), fatigue=10)
    state = _snapshot(authority, reload_action, move)
    combatants = tuple(
        replace(
            actor,
            resources=replace(actor.resources, fatigue_capacity=KnownValue.exact(25)),
        )
        if actor.actor_id == "brother"
        else actor
        for actor in state.combatants
    )
    state = rebuild(state, combatants=combatants)
    reload_action = by_skill(state, "actives.reload_bolt")
    move = by_kind(state, ActionKind.MOVE_TO)
    return fixture(
        "t25-quality-fatigue-sustainable",
        state,
        ("fatigue_resource_economy", "movement_path_zoc"),
        "make the future-capacity cost of a fatigue-heavy action explicit against a more sustainable current move",
        "the supported reload adds 20 FAT while the supplied move adds 10 FAT at 25 capacity; #5 requires headroom and current-template lockout to remain inspectable",
        {
            "expected_status": "SUCCESS",
            "exact_legal_action_ids": exact_ids(state),
            "numeric_relations": [
                relation(
                    move.action_id,
                    "evaluation.features.resources.fatigue_headroom.expected",
                    ">",
                    right_id=reload_action.action_id,
                    right_path="evaluation.features.resources.fatigue_headroom.expected",
                ),
                relation(
                    move.action_id,
                    "evaluation.features.future_capacity.ap_fat_feasible_template_count.expected",
                    ">",
                    right_id=reload_action.action_id,
                    right_path="evaluation.features.future_capacity.ap_fat_feasible_template_count.expected",
                ),
            ],
        },
    )


def quality_recover_tradeoff() -> FixtureEnvelope:
    authority = _authority()
    state = _snapshot(
        authority,
        _resource_action("actives.recover"),
        _move_action(destination="east", path=("east",)),
    )
    combatants = tuple(
        replace(actor, resources=replace(actor.resources, fatigue=KnownValue.exact(80)))
        if actor.actor_id == "brother"
        else actor
        for actor in state.combatants
    )
    state = rebuild(state, combatants=combatants)
    recover = by_skill(state, "actives.recover")
    move = by_kind(state, ActionKind.MOVE_TO)
    return fixture(
        "t25-quality-recover-tradeoff",
        state,
        ("fatigue_resource_economy", "tempo_wait_end_turn"),
        "encode Recover versus acting as an explicit headroom-versus-residual-AP tradeoff without forcing a debatable golden move",
        "Recover is a supported deterministic resource skill; #10 says ambiguous tactical choices should gate the defensible component relationships instead of hardcoding one human move",
        {
            "expected_status": "SUCCESS",
            "exact_legal_action_ids": exact_ids(state),
            "numeric_relations": [
                relation(
                    recover.action_id,
                    "evaluation.features.resources.fatigue_headroom.expected",
                    ">",
                    right_id=move.action_id,
                    right_path="evaluation.features.resources.fatigue_headroom.expected",
                ),
                relation(
                    move.action_id,
                    "evaluation.features.resources.remaining_action_points.expected",
                    ">",
                    right_id=recover.action_id,
                    right_path="evaluation.features.resources.remaining_action_points.expected",
                ),
            ],
        },
    )


def quality_wait_beneficial() -> FixtureEnvelope:
    state = rebuild(_snapshot(_authority(), _wait(), _wait(ActionKind.END_TURN)))
    wait = wait_action(state)
    end = by_kind(state, ActionKind.END_TURN)
    return fixture(
        "t25-quality-wait-over-end-turn",
        state,
        ("tempo_wait_end_turn",),
        "preserve a legitimate wait opportunity instead of ending the active actor's turn immediately",
        "the deterministic Wait and End Turn transition families are manifest-supported and #5 requires tempo to remain an explicit component",
        {
            "expected_status": "SUCCESS",
            "exact_legal_action_ids": exact_ids(state),
            "acceptable_top1": [wait.action_id],
            "forbidden_top1": [end.action_id],
            "required_orderings": [[wait.action_id, end.action_id]],
            "required_explanations": [
                {"action_id": wait.action_id, "component_ids": ["tempo_turn_order"]}
            ],
        },
    )


def quality_wait_dangerous() -> FixtureEnvelope:
    state = _ordinary_attack_state(_authority(), hit_points=1, head_armor=0, body_armor=0)
    state = add_wait(state)
    attack = by_kind(state, ActionKind.USE_SKILL)
    wait = wait_action(state)
    return fixture(
        "t25-quality-act-now-over-dangerous-wait",
        state,
        ("tempo_wait_end_turn", "obvious_offense_kill_secure"),
        "act now on a clearly removable adjacent threat instead of giving away tempo with Wait",
        "ordinary Chop and Wait are supported; the 1-HP visible target makes the act-now relationship a defensible tempo/offense gate rather than a calibration guess",
        {
            "expected_status": "SUCCESS",
            "exact_legal_action_ids": exact_ids(state),
            "acceptable_top1": [attack.action_id],
            "forbidden_top1": [wait.action_id],
            "required_orderings": [[attack.action_id, wait.action_id]],
            "numeric_relations": [
                relation(
                    attack.action_id,
                    "evaluation.features.enemy_effect.kill_probability.expected",
                    ">",
                    right_id=wait.action_id,
                    right_path="evaluation.features.enemy_effect.kill_probability.expected",
                )
            ],
        },
    )


def quality_near_tie() -> FixtureEnvelope:
    state = rebuild(
        _scenario_flip_state(_authority(), omniscient_hp=10),
        raw_capture_id="t25-capture-near-tie",
    )
    first = by_target(state, "enemy")
    second = by_target(state, "enemy-2")
    return fixture(
        "t25-quality-near-tie-equal-targets",
        state,
        ("control_disable_threat_priority", "obvious_offense_kill_secure"),
        "treat two materially equivalent attacks on symmetric equal-state targets as multiple reasonable expert choices",
        "#10 permits acceptable sets and near-tie assertions instead of arbitrary one-action truth; both supported attacks face equivalent exact target state",
        {
            "expected_status": "SUCCESS",
            "exact_legal_action_ids": exact_ids(state),
            "acceptable_top1": [first.action_id, second.action_id],
            "top_k": [{"any_of": [first.action_id, second.action_id], "k": 2}],
            "near_ties": [{"action_ids": [first.action_id, second.action_id], "expected": True}],
        },
    )


def quality_threat_priority() -> FixtureEnvelope:
    state = rebuild(_scenario_flip_state(_authority(), omniscient_hp=5))
    weak = by_target(state, "enemy")
    reference = by_target(state, "enemy-2")
    return fixture(
        "t25-quality-supported-threat-priority",
        state,
        ("control_disable_threat_priority", "obvious_offense_kill_secure"),
        "prioritize removal of the more immediately removable exact target using only the supported ordinary-attack family",
        "the manifest has no broad control family in M1, so #25's control/threat-priority coverage uses the supported threat-removal dimension without fabricating stun/net mechanics",
        {
            "expected_status": "SUCCESS",
            "exact_legal_action_ids": exact_ids(state),
            "acceptable_top1": [weak.action_id],
            "forbidden_top1": [reference.action_id],
            "required_orderings": [[weak.action_id, reference.action_id]],
        },
    )


def stable_player_state() -> TacticalState:
    authority = _authority()
    state = _ordinary_attack_state(authority, hit_points=60, head_armor=40, body_armor=70)
    enemy = next(actor for actor in state.combatants if actor.actor_id == "enemy")
    uncertain = replace(
        enemy,
        resources=replace(
            enemy.resources,
            hit_points=KnownValue(
                Representation.SET,
                KnowledgeClass.INFERRED,
                candidates=(40, 60),
                basis=("visible-wound-band",),
            ),
            head_armor=KnownValue(
                Representation.SET,
                KnowledgeClass.INFERRED,
                candidates=(40, 50),
                basis=("visible-helmet-band",),
            ),
            body_armor=KnownValue(
                Representation.SET,
                KnowledgeClass.INFERRED,
                candidates=(70, 80),
                basis=("visible-armor-band",),
            ),
        ),
    )
    state = rebuild(
        state,
        raw_capture_id="t25-capture-stable",
        information_profile=InformationProfile.PLAYER_LEGAL,
        combatants=tuple(uncertain if actor.actor_id == "enemy" else actor for actor in state.combatants),
    )
    return add_wait(state)


def stable_debug_state() -> TacticalState:
    state = _ordinary_attack_state(_authority(), hit_points=40, head_armor=40, body_armor=70)
    enemy = next(actor for actor in state.combatants if actor.actor_id == "enemy")
    exact = replace(
        enemy,
        resources=replace(
            enemy.resources,
            hit_points=KnownValue.exact(40, KnowledgeClass.DEBUG_GROUND_TRUTH),
            head_armor=KnownValue.exact(40, KnowledgeClass.DEBUG_GROUND_TRUTH),
            body_armor=KnownValue.exact(70, KnowledgeClass.DEBUG_GROUND_TRUTH),
        ),
    )
    state = rebuild(
        state,
        raw_capture_id="t25-capture-stable",
        information_profile=InformationProfile.OMNISCIENT_DEBUG,
        combatants=tuple(exact if actor.actor_id == "enemy" else actor for actor in state.combatants),
    )
    return add_wait(state)


def no_cheat_stable_player() -> FixtureEnvelope:
    state = stable_player_state()
    attack = by_kind(state, ActionKind.USE_SKILL)
    wait = wait_action(state)
    return fixture(
        "t25-no-cheat-stable-player",
        state,
        ("uncertainty_no_cheat", "obvious_offense_kill_secure"),
        "retain a stable attack recommendation across a legal hidden HP/armor belief set without substituting exact debug truth",
        "#6 requires coherent scenario propagation for unweighted SET beliefs; exploration confirmed all eight HP/head/body scenarios retain the same supported top action",
        {
            "expected_status": "SUCCESS",
            "exact_legal_action_ids": exact_ids(state),
            "acceptable_top1": [attack.action_id],
            "forbidden_top1": [wait.action_id],
            "required_orderings": [[attack.action_id, wait.action_id]],
            "information_sensitive": False,
            "numeric_relations": [
                relation(attack.action_id, "evaluation.uncertainty_span", ">", value=0)
            ],
            "required_explanations": [
                {"action_id": attack.action_id, "component_ids": ["uncertainty_robustness_adjustment"]}
            ],
        },
    )


def no_cheat_stable_debug() -> FixtureEnvelope:
    state = stable_debug_state()
    attack = by_kind(state, ActionKind.USE_SKILL)
    wait = wait_action(state)
    return fixture(
        "t25-no-cheat-stable-debug",
        state,
        ("uncertainty_no_cheat", "obvious_offense_kill_secure"),
        "pair the stable player-legal belief fixture with one exact omniscient ground-truth state from the same raw capture",
        "#2 dual-run debugging permits DEBUG_GROUND_TRUTH only in omniscient_debug; combat RNG remains but epistemic uncertainty disappears",
        {
            "expected_status": "SUCCESS",
            "exact_legal_action_ids": exact_ids(state),
            "acceptable_top1": [attack.action_id],
            "forbidden_top1": [wait.action_id],
            "required_orderings": [[attack.action_id, wait.action_id]],
            "information_sensitive": False,
            "numeric_relations": [
                relation(attack.action_id, "evaluation.uncertainty_span", "==", value=0)
            ],
        },
    )


def no_cheat_flip_player() -> FixtureEnvelope:
    state = rebuild(_scenario_flip_state(_authority()), raw_capture_id="t25-capture-flip")
    uncertain = by_target(state, "enemy")
    return fixture(
        "t25-no-cheat-flip-player",
        state,
        ("uncertainty_no_cheat", "control_disable_threat_priority"),
        "surface a recommendation as information-sensitive when plausible hidden HP states reverse the preferred target",
        "#6 coherent epistemic scenarios use enemy HP SET {5,20}; one plausible state prefers enemy while the other prefers enemy-2, so sensitivity must be explicit",
        {
            "expected_status": "SUCCESS",
            "exact_legal_action_ids": exact_ids(state),
            "information_sensitive": True,
            "numeric_relations": [
                relation(uncertain.action_id, "evaluation.uncertainty_span", ">", value=0)
            ],
            "required_explanations": [
                {"action_id": uncertain.action_id, "component_ids": ["uncertainty_robustness_adjustment"]}
            ],
        },
    )


def flip_debug(hp: int, fixture_id: str) -> FixtureEnvelope:
    state = rebuild(
        _scenario_flip_state(_authority(), omniscient_hp=hp),
        raw_capture_id="t25-capture-flip",
    )
    enemy = by_target(state, "enemy")
    enemy2 = by_target(state, "enemy-2")
    chosen = enemy if hp == 5 else enemy2
    other = enemy2 if hp == 5 else enemy
    return fixture(
        fixture_id,
        state,
        ("uncertainty_no_cheat", "control_disable_threat_priority"),
        f"resolve the shared flip capture under exact omniscient enemy HP {hp} without epistemic sensitivity",
        "#2 permits exact hidden ground truth only under omniscient_debug; #6 requires epistemic scenarios to disappear while ordinary combat RNG remains",
        {
            "expected_status": "SUCCESS",
            "exact_legal_action_ids": exact_ids(state),
            "acceptable_top1": [chosen.action_id],
            "forbidden_top1": [other.action_id],
            "required_orderings": [[chosen.action_id, other.action_id]],
            "information_sensitive": False,
            "numeric_relations": [
                relation(enemy.action_id, "evaluation.uncertainty_span", "==", value=0),
                relation(enemy2.action_id, "evaluation.uncertainty_span", "==", value=0),
            ],
        },
    )


def no_cheat_preview_hidden_defense() -> FixtureEnvelope:
    state = stable_player_state()
    enemy = next(actor for actor in state.combatants if actor.actor_id == "enemy")
    state = rebuild(
        state,
        raw_capture_id="t25-capture-preview",
        combatants=tuple(
            replace(enemy, tactical_stats=()) if actor.actor_id == "enemy" else actor
            for actor in state.combatants
        ),
    )
    attack = by_kind(state, ActionKind.USE_SKILL)
    wait = wait_action(state)
    return fixture(
        "t25-no-cheat-preview-hidden-defense",
        state,
        ("uncertainty_no_cheat", "core_legality_affordability"),
        "use the legitimate displayed 67% hit chance while exact hidden enemy defense remains absent from player-legal state",
        "#13 makes displayed current hit chance legitimate terminal preview input and #2 forbids inferring the hidden defense stat that Battle Brothers used internally",
        {
            "expected_status": "SUCCESS",
            "exact_legal_action_ids": exact_ids(state),
            "acceptable_top1": [attack.action_id],
            "forbidden_top1": [wait.action_id],
            "required_orderings": [[attack.action_id, wait.action_id]],
            "information_sensitive": False,
            "action_facts": [
                {
                    "action_id": attack.action_id,
                    "path": "preview.displayed_hit_chance.value",
                    "equals": 67,
                }
            ],
        },
    )


def no_cheat_uncertain_position() -> FixtureEnvelope:
    authority = _authority()
    wait = _wait()
    base = _snapshot(authority, wait)
    brother = next(actor for actor in base.combatants if actor.actor_id == "brother")
    enemy = next(actor for actor in base.combatants if actor.actor_id == "enemy")
    enemy = replace(
        enemy,
        visible=False,
        position=KnownValue(
            Representation.SET,
            KnowledgeClass.INFERRED,
            candidates=("adjacent", "far"),
            basis=("last-seen-and-current-visibility-bounds",),
        ),
    )
    combatants = (_known_position(brother, "origin"), enemy)
    coordinates = {
        "origin": (0, 0),
        "adjacent": (1, 0),
        "middle": (2, 0),
        "far": (3, 0),
    }
    state = _snapshot(
        authority,
        wait,
        information_profile=InformationProfile.PLAYER_LEGAL,
        combatants=combatants,
        tiles=_tiles(coordinates, combatants),
    )
    state = rebuild(state, raw_capture_id="t25-capture-position-belief")
    wait = wait_action(state)
    return fixture(
        "t25-no-cheat-uncertain-position",
        state,
        ("uncertainty_no_cheat", "elevation_positioning"),
        "preserve hidden hostile position as an inferred finite set instead of inventing a midpoint/current exact tile",
        "#2/#6 require unseen instance location to remain belief-bearing; the threat feature spans zero to one adjacent hostile with no expected midpoint",
        {
            "expected_status": "SUCCESS",
            "exact_legal_action_ids": exact_ids(state),
            "numeric_relations": [
                relation(wait.action_id, "evaluation.features.threat.adjacent_hostile_pressure.minimum", "==", value=0),
                relation(wait.action_id, "evaluation.features.threat.adjacent_hostile_pressure.maximum", "==", value=1),
            ],
        },
    )


def no_cheat_aleatory_only() -> FixtureEnvelope:
    authority = _authority()
    move = _move_action(reactions=(_reaction(),))
    state = _movement_state(authority, move)
    state = rebuild(
        state,
        raw_capture_id="t25-capture-aleatory",
        action_affordances=replace(state.action_affordances, actions=(move, _wait())),
    )
    move = by_kind(state, ActionKind.MOVE_TO)
    wait = wait_action(state)
    return fixture(
        "t25-no-cheat-aleatory-only-debug",
        state,
        ("uncertainty_no_cheat", "movement_path_zoc"),
        "keep ordinary AOO combat RNG visible while reporting zero epistemic uncertainty in an omniscient state",
        "#6 states that omniscient_debug can remove epistemic uncertainty but never aleatory combat RNG; exact AOO enumeration therefore has a damage range with zero uncertainty span",
        {
            "expected_status": "SUCCESS",
            "exact_legal_action_ids": exact_ids(state),
            "acceptable_top1": [wait.action_id],
            "forbidden_top1": [move.action_id],
            "required_orderings": [[wait.action_id, move.action_id]],
            "information_sensitive": False,
            "numeric_relations": [
                relation(
                    move.action_id,
                    "evaluation.features.friendly_harm.expected_self_hp_damage.maximum",
                    ">",
                    right_id=move.action_id,
                    right_path="evaluation.features.friendly_harm.expected_self_hp_damage.minimum",
                ),
                relation(move.action_id, "evaluation.uncertainty_span", "==", value=0),
            ],
        },
    )


def unit_value_pair() -> tuple[FixtureEnvelope, FixtureEnvelope]:
    loaded = load_fixture(CORE_SAFETY / "t24-safety-high-aoo-10hp.json")
    assert loaded.status is ResultStatus.SUCCESS and loaded.value is not None
    state = rebuild(loaded.value.state, raw_capture_id="t25-capture-unit-value")
    move = by_kind(state, ActionKind.MOVE_TO)
    wait = wait_action(state)
    expectations = {
        "expected_status": "SUCCESS",
        "exact_legal_action_ids": exact_ids(state),
        "acceptable_top1": [wait.action_id],
        "forbidden_top1": [move.action_id],
        "required_orderings": [[wait.action_id, move.action_id]],
        "numeric_relations": [
            relation(move.action_id, "evaluation.tail_risk.selection_penalty", ">", value=0)
        ],
        "required_explanations": [
            {"action_id": move.action_id, "component_ids": ["tail_risk_penalty", "immediate_friendly_harm"]}
        ],
    }
    default = fixture(
        "t25-unit-value-default",
        state,
        ("survival_catastrophic_risk", "uncertainty_no_cheat"),
        "evaluate a vulnerable brother under the default common-preservation UnitValuePolicy",
        "#5/#13 keep strategic friendly-unit value outside TacticalState; this fixture is one half of an identical-state policy pair",
        expectations,
    )
    high = fixture(
        "t25-unit-value-high",
        state,
        ("survival_catastrophic_risk", "uncertainty_no_cheat"),
        "evaluate the identical vulnerable-brother state with an explicitly higher strategic UnitValuePolicy supplied only by evaluation context",
        "#10 requires an identical-state policy pair proving unit value changes friendly-loss/tail-risk valuation without a BB-Save-Toolkit runtime dependency",
        expectations,
    )
    return default, high


def no_cheat_failure_health() -> FixtureEnvelope:
    state = rebuild(
        _snapshot(_authority(), _wait(), _attack("mod.unknown_aoe")),
        raw_capture_id="t25-capture-coverage-health",
    )
    return fixture(
        "t25-no-cheat-coverage-failure-health",
        state,
        ("uncertainty_no_cheat", "trace_failure_coverage"),
        "retain a complete player-legal current action set while an unsupported special action fails coverage visibly instead of receiving a guessed score",
        "#13 unsupported-material-affordance behavior and #25 trace/failure-health scope require an inspectable INCOMPLETE_COVERAGE result under player_legal",
        {
            "expected_status": "INCOMPLETE_COVERAGE",
            "exact_legal_action_ids": exact_ids(state),
            "expected_problem_codes": ["EVALUATION_UNSUPPORTED"],
            "expected_mechanic_ids": ["mod.unknown_aoe"],
        },
        severity=FixtureSeverity.CORE,
    )


def build_all() -> tuple[FixtureEnvelope, ...]:
    unit_default, unit_high = unit_value_pair()
    return (
        quality_zero_damage_protect(),
        quality_high_ground(),
        quality_surround_control(),
        quality_escape_flexibility(),
        quality_fatigue_sustainable(),
        quality_recover_tradeoff(),
        quality_wait_beneficial(),
        quality_wait_dangerous(),
        quality_near_tie(),
        quality_threat_priority(),
        no_cheat_stable_player(),
        no_cheat_stable_debug(),
        no_cheat_flip_player(),
        flip_debug(5, "t25-no-cheat-flip-debug-low"),
        flip_debug(20, "t25-no-cheat-flip-debug-high"),
        no_cheat_preview_hidden_defense(),
        no_cheat_uncertain_position(),
        no_cheat_aleatory_only(),
        unit_default,
        unit_high,
        no_cheat_failure_health(),
    )


def main() -> None:
    CORPUS.mkdir(parents=True, exist_ok=True)
    fixtures = build_all()
    assert len(fixtures) == 21
    assert len({item.metadata.fixture_id for item in fixtures}) == len(fixtures)
    for item in fixtures:
        result = save_fixture(CORPUS / f"{item.metadata.fixture_id}.json", item)
        assert result.status is ResultStatus.SUCCESS, result.problems

    loaded_25 = []
    for path in sorted(CORPUS.glob("*.json")):
        loaded = load_fixture(path)
        assert loaded.status is ResultStatus.SUCCESS, loaded.problems
        assert loaded.value is not None
        loaded_25.append(loaded.value)
    assert len(loaded_25) == 21
    assert sum("uncertainty_no_cheat" in item.metadata.taxonomy for item in loaded_25) >= 8

    loaded_all = []
    for directory in (CORE_SAFETY, CORPUS):
        for path in sorted(directory.glob("*.json")):
            loaded = load_fixture(path)
            assert loaded.status is ResultStatus.SUCCESS, loaded.problems
            assert loaded.value is not None
            loaded_all.append(loaded.value)
    report = run_validation_corpus(_authority(), loaded_all)
    if not report.passed:
        for fixture_report in report.fixtures:
            for failure in fixture_report.blocking_failures:
                print(
                    "FAIL",
                    fixture_report.fixture_id,
                    failure.assertion_id,
                    failure.message,
                )
        raise AssertionError("combined #24/#25 corpus has blocking failures")
    assert report.coverage.total_fixtures == 54
    assert report.coverage.gated_fixtures == 54
    assert report.coverage.safety_critical_fixtures == 10
    print("validated 21 ticket #25 fixtures; combined gated corpus 54 with 10 safety")


if __name__ == "__main__":
    main()
