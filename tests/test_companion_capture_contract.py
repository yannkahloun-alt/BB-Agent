from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
SUBSTRATE = ROOT / "companion_mod/scripts/bb_agent/capture_substrate.nut"
PROVENANCE = ROOT / "companion_mod/scripts/bb_agent/runtime_provenance.nut"
HOOK = ROOT / "companion_mod/scripts/bb_agent/hooks/tactical_state.nut"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_companion_preload_uses_modern_hooks_and_script_paths() -> None:
    text = _read(PRELOAD)
    assert "::Hooks.register(def.ID, def.Version, def.Name)" in text
    assert '::include("scripts/bb_agent/capture_substrate")' in text
    assert '::include("scripts/bb_agent/runtime_provenance")' in text
    assert '::include("scripts/bb_agent/hooks/tactical_state")' in text


def test_command_ready_predicate_keeps_all_frozen_guards() -> None:
    text = _read(SUBSTRATE)
    required = (
        "isBattleEnded()",
        "isPaused()",
        "getActiveEntity()",
        "isAlive()",
        "isPlacedOnMap()",
        "isPlayerControlled()",
        "isTurnStarted()",
        "isTurnDone()",
        "isInputLocked()",
        "getCurrentActionState() != null",
        "getSkills().isBusy()",
        "getNavigator().isTravelling(active)",
        "hasEventScheduled(::TimeUnit.Virtual)",
        "IsShowingFleeScreen",
        "IsExitingToMenu",
    )
    for guard in required:
        assert guard in text, guard


def test_lifecycle_is_post_update_and_fails_closed() -> None:
    hook = _read(HOOK)
    substrate = _read(SUBSTRATE)
    update = hook.index("q.onUpdate")
    original = hook.index("__original();", update)
    observe = hook.index("::BBAGENT_Capture.observe(this);", update)
    assert original < observe
    assert "::BBAGENT_Capture.isRuntimeCompatible()" in hook
    assert '::BBAGENT_Capture.invalidate("runtime_incompatible")' in hook
    assert 'RecordType = "DECISION_READY"' in substrate
    assert 'RecordType = "DECISION_INVALIDATED"' in substrate
    assert "this.invalidate(readiness.Reason);" in substrate
    assert 'this.invalidate("capture_error");' in substrate
    assert "++this.State.SourceGeneration" in substrate
    assert "LastReadySignature == signature" in substrate


def test_continuous_identical_ready_poll_does_not_emit_duplicate_event() -> None:
    text = _read(SUBSTRATE)
    assert "local wasReady = this.State.IsReady;" in text
    assert "if (duplicate && wasReady) return null;" in text
    assert "Duplicate = duplicate" in text


def test_runtime_provenance_is_probed_and_mismatches_fail_closed() -> None:
    preload = _read(PRELOAD)
    provenance = _read(PROVENANCE)
    hook = _read(HOOK)

    assert 'capture.SupportedRuntimeGameVersion <- "1.5.2.2"' in provenance
    assert "::GameInfo.getVersionNumber()" in provenance
    assert "::Const.Serialization.Version" in provenance
    assert "::Hooks.getMods()" in provenance
    assert "mod.getVersionString()" in provenance
    assert 'reason = "game_version_mismatch"' in provenance
    assert 'reason = "unsupported_mod_stack"' in provenance
    assert 'reason = "explicit_provenance_mismatch"' in provenance
    assert "UnsupportedMods = runtimeMods.Unsupported" in provenance
    assert "IsCompatible = reason == null" in provenance
    assert "capture._refreshRuntimeProvenance();" in provenance
    assert '::include("scripts/bb_agent/runtime_provenance")' in preload
    assert "::BBAGENT_Capture._refreshRuntimeProvenance();" in hook
    assert "::BBAGENT_Capture.isRuntimeCompatible()" in hook
    assert "catch (error)" in provenance
    assert 'return this._setProvenanceFailure("runtime_provenance_error");' in provenance
    assert 'GameVersion = "unknown"' in provenance
    assert "IsCompatible = false" in provenance
    assert provenance.count('this.invalidate("runtime_incompatible");') >= 2

    for allowed in (
        "vanilla = true",
        "dlc_lindwurm = true",
        "dlc_unhold = true",
        "dlc_wildmen = true",
        "dlc_desert = true",
        "dlc_paladins = true",
        "mod_modern_hooks = true",
        "mod_bb_agent_capture = true",
    ):
        assert allowed in provenance, allowed


def test_explicit_provenance_expectation_survives_runtime_refresh() -> None:
    provenance = _read(PROVENANCE)
    assert "capture.ExpectedProvenance <- null;" in provenance
    assert "function(_runtimeGameVersion, _runtimeMods)" in provenance
    assert "if (this.ExpectedProvenance == null) return true;" in provenance
    assert "this.ExpectedProvenance.GameVersion == _runtimeGameVersion" in provenance
    assert (
        "this.ExpectedProvenance.RulesetGameVersion == this.SupportedGameVersion"
        in provenance
    )
    assert (
        "this.ExpectedProvenance.RulesetContentFingerprint == this.RulesetContentFingerprint"
        in provenance
    )
    assert (
        "this._arraysEqual(this.ExpectedProvenance.Mods, _runtimeMods.Identities)"
        in provenance
    )
    assert "this.ExpectedProvenance = {" in provenance
    assert "return this._refreshRuntimeProvenance();" in provenance

    configured = provenance.index("capture.configureProvenance = function")
    assign = provenance.index("this.ExpectedProvenance = {", configured)
    refresh = provenance.index("return this._refreshRuntimeProvenance();", assign)
    assert configured < assign < refresh


def test_capture_substrate_has_no_execution_or_gameplay_rng_path() -> None:
    combined = _read(PRELOAD) + _read(SUBSTRATE) + _read(PROVENANCE) + _read(HOOK)
    forbidden = (
        "Math.rand(",
        "::Math.rand(",
        "getNavigator().travel(",
        ".use(",
        ".wait(",
        ".endTurn(",
        ".endTurnAll(",
        "onEntitySkillClicked(",
        "onWaitPressed(",
        "onEndTurnPressed(",
    )
    for token in forbidden:
        assert token not in combined, token


def test_rich_raw_state_is_in_process_and_not_logged_or_serialized() -> None:
    text = _read(SUBSTRATE)
    provenance = _read(PROVENANCE)
    assert "CurrentRaw" in text
    assert "RawSourceFingerprintInputs" in text
    assert "ActiveActor = _active" in text
    assert "EntityManager = ::Tactical.Entities" in text
    assert "ObservationMemory" in text
    assert "JSON.stringify" not in text
    assert "json.stringify" not in text
    assert "JSON.stringify" not in provenance
    assert "json.stringify" not in provenance

    log_lines = [
        line for line in (text + "\n" + provenance).splitlines() if "::log" in line
    ]
    joined = "\n".join(log_lines)
    for forbidden in (
        "CurrentRaw",
        "RawSourceFingerprintInputs",
        "LastReadySignature",
        "getCurrentProperties",
        "getAllInstances",
    ):
        assert forbidden not in joined


def test_observation_memory_is_separate_and_player_legal_only_api() -> None:
    text = _read(SUBSTRATE)
    assert "rememberPlayerLegalFact" in text
    assert "forgetPlayerLegalFact" in text
    assert "getObservationMemory" in text
    assert "Raw runtime objects must never be inserted into ObservationMemory" in text
    acquisition = text[
        text.index("function _acquireRaw") : text.index("function observe")
    ]
    assert "ObservationMemory" not in acquisition


def test_fingerprint_material_is_deterministic_and_versioned() -> None:
    text = _read(SUBSTRATE)
    assert '"capture_contract=" + this.CaptureContractVersion' in text
    assert '"game_version=" + this.State.Provenance.GameVersion' in text
    assert '"ruleset_game_version=" + this.State.Provenance.RulesetGameVersion' in text
    assert (
        '"ruleset_content=" + this.State.Provenance.RulesetContentFingerprint' in text
    )
    assert '"battle=" + this.State.BattleSequence' in text
    assert '"round=" + turnBar.getCurrentRound()' in text
    assert '"turn_position=" + turnBar.getTurnPosition()' in text
    assert '"active_actor=" + _active.getID()' in text
    assert "ret.sort();" in text
    assert 'return _inputs.join("\\x1f");' in text
    assert "#57 converts these stable" in text


def test_fingerprint_covers_turn_order_and_map_semantics() -> None:
    text = _read(SUBSTRATE)
    required = (
        "function _turnSequenceTokens()",
        "getCurrentEntities()",
        'ret.push("turn=" + index + ":" + actor.getID());',
        "function _mapTokens()",
        "::Tactical.getMapSize()",
        "::Tactical.isValidTileSquare(x, y)",
        "::Tactical.getTileSquare(x, y)",
        '":level=" + tile.Level',
        '":type=" + tile.Type',
        '":subtype=" + tile.Subtype',
        '":empty=" + this._boolToken(tile.IsEmpty)',
        '":visible=" + this._boolToken(tile.IsVisibleForPlayer)',
        '":discovered=" + this._boolToken(tile.IsDiscovered)',
        "foreach (turnToken in this._turnSequenceTokens())",
        "foreach (mapToken in this._mapTokens())",
    )
    for token in required:
        assert token in text, token


def test_affordance_generation_uses_active_player_oracles_only() -> None:
    text = _read(SUBSTRATE)
    raw_skill_tokens = text[
        text.index("function _skillTokens") : text.index(
            "function _activeAffordanceTokens"
        )
    ]
    assert "skill.m" in raw_skill_tokens
    for forbidden in (
        "queryActives()",
        "isUsable()",
        "isAffordable()",
        "getActionPointCost()",
        "getFatigueCost()",
    ):
        assert forbidden not in raw_skill_tokens, forbidden

    affordance_tokens = text[
        text.index("function _activeAffordanceTokens") : text.index(
            "function _itemTokens"
        )
    ]
    for required in (
        "_active.getSkills().queryActives()",
        "skill.isUsable()",
        "skill.isAffordable()",
        "skill.getActionPointCost()",
        "skill.getFatigueCost()",
        "skill.isTargeted()",
        "skill.isTargetingActor()",
        "skill.getMinRange()",
        "skill.getMaxRange()",
        "skill.getMaxLevelDifference()",
    ):
        assert required in affordance_tokens, required

    fingerprint = text[
        text.index("function _fingerprintInputs") : text.index(
            "function _sourceSignature"
        )
    ]
    assert "this._activeAffordanceTokens(_active)" in fingerprint
    assert '"may_wait_actor=" + this._boolToken(_active.isAbleToWait())' in fingerprint
    assert (
        '"may_wait_bar=" + this._boolToken(turnBar.canEntityWait(_active))'
        in fingerprint
    )


def test_battle_lifecycle_resets_memory_and_generation() -> None:
    text = _read(SUBSTRATE)
    begin = text[text.index("function beginBattle") : text.index("function endBattle")]
    assert "++this.State.BattleSequence" in begin
    assert "this.State.SourceGeneration = -1" in begin
    assert "this.State.LastReadySignature = null" in begin
    assert "this.State.ObservationMemory = {}" in begin
    hook = _read(HOOK)
    assert "::BBAGENT_Capture.beginBattle();" in hook
    assert "::BBAGENT_Capture._refreshRuntimeProvenance();" in hook
    assert '::BBAGENT_Capture.endBattle("battle_ended");' in hook
    assert '::BBAGENT_Capture.endBattle("tactical_state_destroyed");' in hook
