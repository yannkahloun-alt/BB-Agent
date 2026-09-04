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
from bb_agent.results import ErrorCode, ResultStatus
from bb_agent.serialization import canonical_sha256
from bb_agent.tactical_state import (
    ActionKind,
    AffordanceCompleteness,
    ItemState,
    KnownValue,
    PlayerVisiblePreview,
    ResolutionAuthority,
    ResolutionStage,
    ResolvedPreviewValue,
    SkillState,
    TacticalState,
    TargetKind,
)
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
    assert all(
        family.status is CoverageStatus.EVALUATION_UNSUPPORTED
        for family in authority.manifest.families
    )
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
    assert result.status is ResultStatus.INCOMPLETE_COVERAGE
    assert len(result.value.affordances) == 2


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


def test_move_requires_aoo_even_when_movement_stub_is_supported(tmp_path):
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
    assert result.status is ResultStatus.INCOMPLETE_COVERAGE
    assert result.value.affordances[0].family_ids == ("aoo", "move")
    assert any(problem.mechanic_id == "aoo" for problem in result.problems)
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
    assert pending.classify(state).status is ResultStatus.INCOMPLETE_COVERAGE
    assert enabled.manifest.fingerprint != pending.manifest.fingerprint


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
        data["families"][0].update(status="SUPPORTED", reason=None)
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
        ResultStatus.SUCCESS if case == "known" else ResultStatus.INCOMPLETE_COVERAGE
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
