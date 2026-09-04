import json
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from bb_agent.mechanics import (
    MANDATORY_FAMILIES,
    CoverageStatus,
    MechanicsAuthority,
    ResolutionLedger,
    RulesStage,
    load_builtin_mechanics,
    load_catalog,
    load_manifest,
)
from bb_agent.outcomes import HitResult, evaluate_ordinary_attack
from bb_agent.results import ErrorCode, ResultStatus
from bb_agent.serialization import canonical_sha256
from bb_agent.tactical_state import (
    ActionKind,
    AffordanceCompleteness,
    ContingentReaction,
    HexCoord,
    InformationProfile,
    ItemState,
    KnowledgeClass,
    KnownValue,
    LifeState,
    PlayerVisiblePreview,
    Representation,
    ResolutionAuthority,
    ResolutionStage,
    ResolvedPreviewValue,
    SkillState,
    TacticalState,
    TargetKind,
    Tile,
)
from bb_agent.transitions import evaluate_transition
from test_tactical_state import _state

DATA = Path(__file__).parents[1] / "src" / "bb_agent" / "data"


def _authority() -> MechanicsAuthority:
    result = load_builtin_mechanics()
    assert result.status is ResultStatus.SUCCESS
    assert result.value is not None
    return result.value


def _write(tmp_path, name, value):
    path = tmp_path / name
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _enabled(tmp_path, *names):
    authority = _authority()
    data = json.loads((DATA / "manifest.v1.json").read_text())
    for family in data["families"]:
        if family["family_id"] in names:
            family.update(
                status="SUPPORTED", model_version="test-validation-stub.v1", reason=None
            )
    result = load_manifest(_write(tmp_path, "manifest.json", data), authority.catalog)
    assert result.value is not None
    return MechanicsAuthority(authority.catalog, result.value)


def _snapshot(authority, *actions, **changes):
    state = _state()
    actors = tuple(
        replace(
            actor,
            skills=tuple(
                SkillState(
                    skill, KnownValue.exact(True), enabled=KnownValue.exact(True)
                )
                for skill in sorted(
                    {action.skill_id for action in actions if action.skill_id}
                )
            ),
        )
        if actor.actor_id == "brother"
        else actor
        for actor in state.combatants
    )
    values = {field.name: getattr(state, field.name) for field in fields(state)}
    values.update(
        state_id="",
        ruleset=authority.catalog.ruleset,
        combatants=actors,
        action_affordances=replace(state.action_affordances, actions=actions),
    )
    values.update(changes)
    return TacticalState.create(**values)


def _attack(skill_id="actives.chop", **changes):
    action = _state().action_affordances.actions[0]
    return replace(action, skill_id=skill_id, **changes)


def _ordinary_attack_state(authority, *, hit_points=60, head_armor=40, body_armor=70):
    state = _snapshot(authority, _attack())
    actors = []
    for actor in state.combatants:
        if actor.actor_id == "brother":
            actors.append(
                replace(
                    actor,
                    perks=KnownValue.exact([]),
                    traits=KnownValue.exact([]),
                    equipment=(
                        ItemState(
                            "hand-axe",
                            KnownValue.exact("weapon.hand_axe"),
                            KnownValue.exact("mainhand"),
                            KnownValue.exact(True),
                        ),
                    ),
                )
            )
        else:
            actors.append(
                replace(
                    actor,
                    perks=KnownValue.exact([]),
                    traits=KnownValue.exact([]),
                    resources=replace(
                        actor.resources,
                        hit_points=KnownValue.exact(hit_points),
                        head_armor=KnownValue.exact(head_armor),
                        body_armor=KnownValue.exact(body_armor),
                    ),
                )
            )
    values = {field.name: getattr(state, field.name) for field in fields(state)}
    values.update(
        state_id="",
        information_profile=InformationProfile.OMNISCIENT_DEBUG,
        combatants=tuple(actors),
    )
    return TacticalState.create(**values)


def _wait(kind=ActionKind.WAIT):
    return replace(
        _attack(),
        kind=kind,
        skill_id=None,
        target_kind=None,
        target_actor_id=None,
        preview=PlayerVisiblePreview(),
    )


def test_builtin_is_pinned_immutable_and_honest():
    authority = _authority()
    assert {
        family.family_id for family in authority.manifest.families
    } == MANDATORY_FAMILIES
    assert (
        authority.manifest.family("ordinary_attack").status is CoverageStatus.SUPPORTED
    )
    assert authority.manifest.family("move").model_version == "transitions.v1"
    assert (
        authority.catalog.provenance.revision
        == "162f498ac7c49b4c317bbf54718a595ecef6a65a"
    )
    assert dict(authority.catalog.entry("weapon.hand_axe").facts)["damage_max"] == 45
    with pytest.raises(FrozenInstanceError):
        authority.catalog.game_version = "changed"
    with pytest.raises(TypeError):
        authority.catalog.entries[0].facts[0] = ("changed", 1)
    result = authority.classify(_snapshot(authority, _attack(), _wait()))
    assert result.status is ResultStatus.SUCCESS
    assert len(result.value.affordances) == 2


def test_ordinary_attack_uses_independent_rolls_and_pinned_damage_formula():
    authority = _authority()
    state = _ordinary_attack_state(
        authority, hit_points=60, head_armor=40, body_armor=70
    )
    action = state.action_affordances.actions[0]

    result = evaluate_ordinary_attack(authority, state, action)

    assert result.status is ResultStatus.SUCCESS
    assert result.value is not None
    outcome = result.value
    assert outcome.probability_mass == pytest.approx(1)
    assert outcome.epistemic is False
    assert outcome.branches[0].result is HitResult.MISS
    assert outcome.branches[0].probability == pytest.approx(0.33)
    head = next(
        branch
        for branch in outcome.branches
        if branch.result is HitResult.HEAD
        and branch.damage == 30
        and branch.armor_damage == pytest.approx(36)
    )
    assert head.hp_damage == 13
    assert head.target_head_armor == pytest.approx(4)
    assert head.actor_action_points == 5
    assert head.actor_fatigue == 10


def test_ordinary_attack_envelope_does_not_invent_set_prior():
    authority = _authority()
    state = _ordinary_attack_state(authority)
    target = next(actor for actor in state.combatants if actor.actor_id == "enemy")
    uncertain_target = replace(
        target,
        resources=replace(
            target.resources,
            hit_points=KnownValue(
                Representation.SET,
                KnowledgeClass.INFERRED,
                candidates=(10, 60),
                basis=("visible-wound",),
            ),
            head_armor=KnownValue(
                Representation.RANGE,
                KnowledgeClass.INFERRED,
                minimum=40,
                maximum=40,
                basis=("visible-helmet",),
            ),
            body_armor=KnownValue(
                Representation.RANGE,
                KnowledgeClass.INFERRED,
                minimum=70,
                maximum=70,
                basis=("visible-body-armor",),
            ),
        ),
    )
    values = {field.name: getattr(state, field.name) for field in fields(state)}
    values.update(
        state_id="",
        information_profile=InformationProfile.PLAYER_LEGAL,
        combatants=tuple(
            uncertain_target if actor.actor_id == "enemy" else actor
            for actor in state.combatants
        ),
    )
    player_legal = TacticalState.create(**values)

    result = evaluate_ordinary_attack(
        authority, player_legal, player_legal.action_affordances.actions[0]
    )

    assert result.status is ResultStatus.SUCCESS
    assert result.value is not None
    assert result.value.probability_mass is None
    assert {scenario.target_hp for scenario in result.value.epistemic_scenarios} == {
        10,
        60,
    }
    assert all(
        scenario.probability_mass == pytest.approx(1)
        for scenario in result.value.epistemic_scenarios
    )


def test_supported_stub_and_unknown_special_propagate_complete_report(tmp_path):
    authority = _enabled(tmp_path, "wait")
    state = _snapshot(authority, _wait(), _attack("mod.unknown_aoe"))
    result = authority.classify(state)
    assert result.status is ResultStatus.INCOMPLETE_COVERAGE
    assert {item.status for item in result.value.affordances} == set(CoverageStatus)
    assert any(problem.mechanic_id == "mod.unknown_aoe" for problem in result.problems)
    assert result == authority.classify(state)
    assert result.value.manifest_fingerprint == authority.manifest.fingerprint
    only_wait = authority.classify(_snapshot(authority, _wait()))
    assert only_wait.status is ResultStatus.SUCCESS
    assert only_wait.value.affordances[0].model_versions == (
        ("wait", "test-validation-stub.v1"),
    )
    reordered = replace(
        state,
        action_affordances=replace(
            state.action_affordances,
            actions=tuple(reversed(state.action_affordances.actions)),
        ),
    )
    assert authority.classify(reordered) == result


@pytest.mark.parametrize(
    "changes",
    [
        {"mode_variant": "special"},
        {"parameters": (("extension.special", KnownValue.exact(True)),)},
        {
            "target_kind": TargetKind.AREA,
            "target_actor_id": None,
            "target_tile_id": "east",
        },
        {
            "preview": PlayerVisiblePreview(
                facts=(
                    (
                        "special",
                        ResolvedPreviewValue(
                            True,
                            ResolutionStage.PREVIEW_RESOLVED,
                            ResolutionAuthority.HANDCRAFTED_FIXTURE,
                        ),
                    ),
                )
            )
        },
    ],
)
def test_ordinary_content_never_accepts_unknown_shape(tmp_path, changes):
    authority = _enabled(tmp_path, "ordinary_attack")
    result = authority.classify(_snapshot(authority, _attack(**changes)))
    assert result.status is ResultStatus.INCOMPLETE_COVERAGE


def test_move_requires_aoo_dependency_and_has_transition_coverage(tmp_path):
    authority = _enabled(tmp_path, "move")
    move = replace(
        _wait(),
        kind=ActionKind.MOVE_TO,
        destination_tile_id="east",
        resolved_path=("east",),
    )
    # Current command legality belongs to source; coverage does not invent paths.
    state = _snapshot(authority, move)
    result = authority.classify(state)
    assert result.status is ResultStatus.SUCCESS
    assert result.value.affordances[0].family_ids == ("aoo", "move")
    enabled = _enabled(tmp_path, "move", "aoo")
    assert enabled.classify(state).status is ResultStatus.SUCCESS


@pytest.mark.parametrize(
    "family,skill", [("recover", "actives.recover"), ("reload", "actives.reload_bolt")]
)
def test_simple_resource_skill_declarations(tmp_path, family, skill):
    authority = _enabled(tmp_path, family)
    action = _attack(skill, target_kind=TargetKind.SELF, target_actor_id=None)
    result = authority.classify(_snapshot(authority, action))
    assert result.status is ResultStatus.SUCCESS
    assert result.value.affordances[0].family_ids == (family,)
    assert (
        authority.classify(_snapshot(authority, _attack(skill))).status
        is ResultStatus.INCOMPLETE_COVERAGE
    )


def test_end_turn_declaration_and_manifest_version_affect_report(tmp_path):
    pending = _authority()
    enabled = _enabled(tmp_path, "end_turn")
    state = _snapshot(enabled, _wait(ActionKind.END_TURN))
    assert enabled.classify(state).status is ResultStatus.SUCCESS
    assert pending.classify(state).status is ResultStatus.SUCCESS
    assert enabled.manifest.fingerprint != pending.manifest.fingerprint


def test_simple_transitions_use_resolved_costs_and_preserve_turn_boundaries():
    authority = _authority()
    state = _snapshot(authority, _wait(), _wait(ActionKind.END_TURN))
    wait = next(
        a for a in state.action_affordances.actions if a.kind is ActionKind.WAIT
    )
    end_turn = next(
        a for a in state.action_affordances.actions if a.kind is ActionKind.END_TURN
    )

    wait_result = evaluate_transition(authority, state, wait)
    assert wait_result.status is ResultStatus.SUCCESS
    wait_branch = wait_result.value.branches[0]
    assert wait_branch.actor_has_waited is True
    assert wait_branch.actor_may_wait is False
    assert wait_branch.turn_ended is False
    assert wait_branch.actor.resources.action_points.value == 5
    assert wait_branch.actor.resources.fatigue.value == 10

    end_result = evaluate_transition(authority, state, end_turn)
    assert end_result.status is ResultStatus.SUCCESS
    assert end_result.value.branches[0].turn_ended is True


@pytest.mark.parametrize(
    "skill,effect",
    [("actives.recover", "fatigue_recovered"), ("actives.reload_bolt", "loaded")],
)
def test_simple_resource_transitions_are_deterministic(skill, effect):
    authority = _authority()
    action = _attack(skill, target_kind=TargetKind.SELF, target_actor_id=None)
    state = _snapshot(authority, action)
    action = state.action_affordances.actions[0]
    result = evaluate_transition(authority, state, action)
    assert result.status is ResultStatus.SUCCESS
    assert result.value.branches[0].effects[0][0] == effect
    assert result.value.branches[0].probability == 1.0


def test_supported_equipment_transition_moves_declared_item_to_declared_slot():
    authority = _authority()
    state = _state()
    item = ItemState(
        "axe",
        KnownValue.exact("weapon.hand_axe"),
        KnownValue.exact("bag"),
        KnownValue.exact(True),
    )
    actors = tuple(
        replace(actor, equipment=(item,)) if actor.actor_id == "brother" else actor
        for actor in state.combatants
    )
    action = replace(
        _wait(),
        kind=ActionKind.EQUIP_ITEM,
        item_id="axe",
        source_location="bag",
        target_slot="mainhand",
    )
    state = _snapshot(authority, action, combatants=actors)
    result = evaluate_transition(authority, state, state.action_affordances.actions[0])
    assert result.status is ResultStatus.SUCCESS
    assert result.value.branches[0].actor.equipment[0].slot.value == "mainhand"


def test_safe_and_unsafe_move_never_repath_or_guess_aoo():
    authority = _authority()
    move = replace(
        _wait(),
        kind=ActionKind.MOVE_TO,
        destination_tile_id="east",
        resolved_path=("east",),
    )
    safe_state = _snapshot(
        authority,
        move,
        combatants=tuple(
            replace(actor, relation=actor.relation.NEUTRAL)
            if actor.actor_id == "enemy"
            else actor
            for actor in _state().combatants
        ),
    )
    safe = evaluate_transition(
        authority, safe_state, safe_state.action_affordances.actions[0]
    )
    assert safe.status is ResultStatus.SUCCESS
    assert safe.value.branches[0].destination_tile_id == "east"
    assert safe.value.branches[0].actor.position.value == "east"

    unsafe_state = _snapshot(authority, move)
    unsafe = evaluate_transition(
        authority, unsafe_state, unsafe_state.action_affordances.actions[0]
    )
    assert unsafe.status is ResultStatus.INCOMPLETE_COVERAGE
    assert unsafe.problems[0].code is ErrorCode.EVALUATION_UNSUPPORTED


def test_supported_lethal_contingent_aoo_interrupts_at_its_trigger_step():
    authority = _authority()
    reactions = tuple(
        ContingentReaction(
            "east",
            actor_id,
            "AOO",
            skill_id="actives.chop",
            hit_chance=ResolvedPreviewValue(
                95,
                ResolutionStage.PREVIEW_RESOLVED,
                ResolutionAuthority.HANDCRAFTED_FIXTURE,
            ),
        )
        for actor_id in ("enemy", "enemy-2")
    )
    move = replace(
        _wait(),
        kind=ActionKind.MOVE_TO,
        destination_tile_id="origin",
        resolved_path=("east", "origin"),
        contingent_reactions=reactions,
    )
    actors = tuple(
        replace(
            actor,
            perks=KnownValue.exact([]),
            traits=KnownValue.exact([]),
            resources=replace(
                actor.resources,
                action_points=KnownValue(
                    Representation.EXACT,
                    KnowledgeClass.DERIVED,
                    value=0,
                    basis=("zero-cost reaction",),
                ),
                fatigue=KnownValue(
                    Representation.EXACT,
                    KnowledgeClass.DERIVED,
                    value=0,
                    basis=("zero-cost reaction",),
                ),
                fatigue_capacity=KnownValue(
                    Representation.EXACT,
                    KnowledgeClass.DERIVED,
                    value=100,
                    basis=("zero-cost reaction",),
                ),
            ),
            equipment=(
                ItemState(
                    "hand-axe",
                    KnownValue.exact("weapon.hand_axe"),
                    KnownValue.exact("mainhand"),
                    KnownValue.exact(True),
                ),
            ),
        )
        if actor.actor_id == "enemy"
        else replace(
            actor,
            perks=KnownValue.exact([]),
            traits=KnownValue.exact([]),
            resources=replace(
                actor.resources,
                hit_points=KnownValue.exact(1),
                head_armor=KnownValue.exact(0),
                body_armor=KnownValue.exact(0),
            ),
        )
        for actor in _state().combatants
    )
    enemy = next(actor for actor in actors if actor.actor_id == "enemy")
    actors += (
        replace(enemy, actor_id="enemy-2", position=KnownValue.exact("southwest")),
    )
    tiles = tuple(
        replace(
            tile,
            neighbors=("east", None, None, None, "southwest", None),
        )
        if tile.tile_id == "origin"
        else tile
        for tile in _state().tiles
    ) + (
        Tile(
            "southwest",
            HexCoord(-1, 1),
            0,
            KnownValue.exact("plain"),
            (None, "origin", None, None, None, None),
            "enemy-2",
        ),
    )
    state = _snapshot(authority, move, combatants=actors, tiles=tiles)

    result = evaluate_transition(authority, state, state.action_affordances.actions[0])

    assert result.status is ResultStatus.SUCCESS
    assert result.value is not None
    killed = [branch for branch in result.value.branches if branch.interrupted]
    assert killed
    assert all(branch.destination_tile_id == "east" for branch in killed)
    assert all(branch.actor.position.value == "east" for branch in killed)
    assert all(branch.actor.life_state is LifeState.REMOVED for branch in killed)
    assert all(branch.effects.count(("aoo", "enemy")) == 1 for branch in killed)
    assert any(("aoo", "enemy-2") not in branch.effects for branch in killed), (
        "a lethal first reaction must suppress the later reaction"
    )


def test_move_costs_fail_closed_when_resolved_resources_are_insufficient():
    authority = _authority()
    move = replace(
        _wait(),
        kind=ActionKind.MOVE_TO,
        destination_tile_id="east",
        resolved_path=("east",),
        ap_cost=replace(_wait().ap_cost, value=10),
    )
    state = _snapshot(
        authority,
        move,
        combatants=tuple(
            replace(actor, relation=actor.relation.NEUTRAL)
            if actor.actor_id == "enemy"
            else actor
            for actor in _state().combatants
        ),
    )

    result = evaluate_transition(authority, state, state.action_affordances.actions[0])

    assert result.status is ResultStatus.INCOMPLETE_COVERAGE
    assert result.problems[0].code is ErrorCode.EVALUATION_UNSUPPORTED
    assert "costs exceed" in result.problems[0].message


def test_displayed_damage_is_terminal_and_subsequent_mitigation_is_allowed():
    preview = ResolvedPreviewValue(
        (30, 45), ResolutionStage.PREVIEW_RESOLVED, ResolutionAuthority.PLAYER_UI
    )
    action = _attack(preview=PlayerVisiblePreview(displayed_damage=preview))
    ledger = ResolutionLedger.for_action_field(action, "displayed_damage")
    assert (
        ledger.apply(RulesStage.CURRENT_DAMAGE_PROFILE).status
        is ResultStatus.VALIDATION_FAILURE
    )
    assert ledger.apply(RulesStage.TARGET_MITIGATION).status is ResultStatus.SUCCESS
    assert action.preview.displayed_damage.value == (30, 45)


@pytest.mark.parametrize(
    "field,value",
    [("game_version", "wrong"), ("content_fingerprint", "wrong"), ("mods", ("mod",))],
)
def test_ruleset_mismatch_is_visible(field, value):
    authority = _authority()
    state = _snapshot(
        authority, _wait(), ruleset=replace(authority.catalog.ruleset, **{field: value})
    )
    result = authority.classify(state)
    assert result.status is ResultStatus.VALIDATION_FAILURE
    assert result.problems[0].code is ErrorCode.CATALOG_MISMATCH


def test_stale_state_and_incomplete_source_cannot_be_coverage_success(tmp_path):
    authority = _enabled(tmp_path, "wait")
    state = _snapshot(authority, _wait())
    for changed in [
        replace(state, state_id="stale"),
        replace(
            state,
            action_affordances=replace(
                state.action_affordances, completeness=AffordanceCompleteness.INCOMPLETE
            ),
        ),
    ]:
        assert authority.classify(changed).status is ResultStatus.VALIDATION_FAILURE


@pytest.mark.parametrize(
    "change",
    [
        "schema",
        "revision",
        "fingerprint",
        "blob",
        "duplicate",
        "unknown_field",
        "nested",
        "nan",
    ],
)
def test_catalog_rejects_malformed_or_mismatched_data(tmp_path, change):
    data = json.loads((DATA / "catalog.v1.json").read_text())
    if change == "schema":
        data["schema_version"] = "future"
    if change == "revision":
        data["provenance"]["revision"] = "main"
    if change == "fingerprint":
        data["entries"][0]["facts"]["base_ap_cost"] += 1
    if change == "blob":
        data["entries"][0]["facts"]["source_blob"] = "latest"
    if change == "duplicate":
        data["entries"].append(data["entries"][0])
    if change == "unknown_field":
        data["surprise"] = True
    if change == "nested":
        data["entries"][0]["facts"]["nested"] = {"x": 1}
    if change == "nan":
        data["entries"][0]["facts"]["bad"] = float("nan")
    result = load_catalog(_write(tmp_path, "catalog.json", data))
    assert result.status is ResultStatus.VALIDATION_FAILURE
    assert result.problems[0].code is ErrorCode.CATALOG_INVALID


@pytest.mark.parametrize(
    "change",
    [
        "version",
        "fingerprint",
        "missing",
        "duplicate",
        "unmapped",
        "wrong_family",
        "dependency",
        "cycle",
        "aoo",
        "model",
    ],
)
def test_manifest_rejects_invalid_coverage_claims(tmp_path, change):
    authority = _authority()
    data = json.loads((DATA / "manifest.v1.json").read_text())
    if change == "version":
        data["version"] = "future"
    if change == "fingerprint":
        data["content_fingerprint"] = "wrong"
    if change == "missing":
        data["families"].pop()
    if change == "duplicate":
        data["families"].append(data["families"][0])
    if change == "unmapped":
        data["families"][0]["content_ids"] = []
    if change == "wrong_family":
        data["families"][0]["content_ids"] = ["actives.recover"]
    if change == "dependency":
        data["families"][0]["requires"] = ["missing"]
    if change == "cycle":
        data["families"][0]["requires"] = ["ordinary_attack"]
    if change == "aoo":
        data["families"][1]["requires"] = []
    if change == "model":
        data["families"][0].update(model_version=None)
    result = load_manifest(_write(tmp_path, "manifest.json", data), authority.catalog)
    assert result.status is ResultStatus.VALIDATION_FAILURE
    assert result.problems[0].code is ErrorCode.MANIFEST_INVALID


def test_missing_and_duplicate_key_files_fail_structurally(tmp_path):
    assert load_catalog(tmp_path / "absent").status is ResultStatus.VALIDATION_FAILURE
    path = tmp_path / "duplicate.json"
    path.write_text('{"x":1,"x":2}')
    assert load_catalog(path).problems[0].message == "duplicate JSON field: x"


def test_static_change_requires_new_identity(tmp_path):
    data = json.loads((DATA / "catalog.v1.json").read_text())
    old = data["content_fingerprint"]
    data["entries"][0]["facts"]["base_ap_cost"] += 1
    data["content_fingerprint"] = canonical_sha256(
        {key: value for key, value in data.items() if key != "content_fingerprint"}
    )
    catalog = load_catalog(_write(tmp_path, "catalog.json", data)).value
    assert catalog is not None and catalog.content_fingerprint != old
    assert (
        load_manifest(DATA / "manifest.v1.json", catalog).status
        is ResultStatus.VALIDATION_FAILURE
    )


@pytest.mark.parametrize("case", ["known", "unknown", "unmapped", "slot", "displaced"])
def test_equipment_coverage_uses_content_and_declared_transition(tmp_path, case):
    authority = _enabled(tmp_path, "equip")
    state = _state()
    content = (
        KnownValue.unknown()
        if case == "unknown"
        else KnownValue.exact("mod.item" if case == "unmapped" else "weapon.hand_axe")
    )
    item = ItemState("axe", content, KnownValue.exact("bag"), KnownValue.exact(True))
    displaced = ItemState(
        "other",
        KnownValue.unknown(),
        KnownValue.exact("mainhand"),
        KnownValue.exact(True),
    )
    actors = tuple(
        replace(actor, equipment=(item, displaced))
        if actor.actor_id == "brother"
        else actor
        for actor in state.combatants
    )
    action = replace(
        _wait(),
        kind=ActionKind.EQUIP_ITEM,
        item_id="axe",
        source_location="bag",
        target_slot="offhand" if case == "slot" else "mainhand",
        displaced_item_id="other" if case == "displaced" else None,
        displaced_item_destination="bag" if case == "displaced" else None,
    )
    result = authority.classify(_snapshot(authority, action, combatants=actors))
    assert result.status is (
        ResultStatus.SUCCESS
        if case in {"known", "displaced"}
        else ResultStatus.INCOMPLETE_COVERAGE
    )


@pytest.mark.parametrize(
    "field,stage",
    [
        ("ap_cost", RulesStage.CURRENT_COST),
        ("fatigue_cost", RulesStage.CURRENT_COST),
        ("displayed_hit_chance", RulesStage.CURRENT_HIT_CHANCE),
    ],
)
def test_resolved_stage_cannot_apply_twice(field, stage):
    action = _attack()
    ledger = ResolutionLedger.for_action_field(action, field)
    result = ledger.apply(stage)
    assert result.status is ResultStatus.VALIDATION_FAILURE
    assert result.problems[0].code is ErrorCode.RESOLUTION_STAGE_CONFLICT
    subsequent = ledger.apply(RulesStage.TARGET_MITIGATION)
    assert subsequent.status is ResultStatus.SUCCESS
    assert subsequent.value.authority == ledger.authority
    assert subsequent.value.apply(stage).status is ResultStatus.VALIDATION_FAILURE


def test_calculated_and_preview_stages_keep_authority_and_reject_ambiguity():
    ledger = ResolutionLedger.calculated("test.v1")
    first = ledger.apply(RulesStage.CURRENT_DAMAGE_PROFILE).value
    assert first.authority == "BB_AGENT_RULES:test.v1"
    assert (
        first.apply(RulesStage.CURRENT_DAMAGE_PROFILE).status
        is ResultStatus.VALIDATION_FAILURE
    )
    action = _attack()
    with pytest.raises(ValueError):
        ResolutionLedger.for_action_field(action, "effective_stat")
    with pytest.raises(ValueError):
        ResolutionLedger.for_action_field(action, "displayed_damage")
    with pytest.raises(ValueError):
        ResolutionLedger.from_resolved(
            replace(action.ap_cost, stage=ResolutionStage.STATIC_RULE),
            RulesStage.CURRENT_COST,
        )
    with pytest.raises(ValueError):
        ResolutionLedger.from_resolved(
            replace(action.ap_cost, authority=ResolutionAuthority.DEBUG_ORACLE),
            RulesStage.CURRENT_COST,
        )
    with pytest.raises(ValueError):
        ResolutionLedger.from_resolved(action.ap_cost, RulesStage.OUTCOME)
