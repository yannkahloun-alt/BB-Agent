local capture = ::BBAGENT_Capture;

// The pinned Battle Brothers source tree was decompiled from runtime v1.5.2.2.
// Do not silently label a different running build as compatible with that tree.
capture.SupportedRuntimeGameVersion <- "1.5.2.2";
capture.AllowedRuntimeModIDs <- {
    vanilla = true,
    dlc_lindwurm = true,
    dlc_unhold = true,
    dlc_wildmen = true,
    dlc_desert = true,
    dlc_paladins = true,
    mod_modern_hooks = true,
    mod_bb_agent_capture = true
};
capture.ExpectedProvenance <- null;

capture._arraysEqual <- function(_left, _right)
{
    if (_left.len() != _right.len()) return false;
    for (local i = 0; i < _left.len(); i = ++i)
    {
        if (_left[i] != _right[i]) return false;
    }
    return true;
};

capture._runtimeModIdentities <- function()
{
    local identities = [];
    local unsupported = [];

    foreach (modID, mod in ::Hooks.getMods())
    {
        identities.push(modID + "@" + mod.getVersionString());
        if (!(modID in this.AllowedRuntimeModIDs)) unsupported.push(modID);
    }

    identities.sort();
    unsupported.sort();
    return {
        Identities = identities,
        Unsupported = unsupported
    };
};

capture._matchesExpectedProvenance <- function(_runtimeGameVersion, _runtimeMods)
{
    if (this.ExpectedProvenance == null) return true;

    return this.ExpectedProvenance.GameVersion == _runtimeGameVersion
        && this.ExpectedProvenance.RulesetGameVersion == this.SupportedGameVersion
        && this.ExpectedProvenance.RulesetContentFingerprint == this.RulesetContentFingerprint
        && this._arraysEqual(this.ExpectedProvenance.Mods, _runtimeMods.Identities);
};

capture._setProvenanceFailure <- function(_reason)
{
    this.State.Provenance = {
        GameVersion = "unknown",
        RuntimeSerializationVersion = null,
        SupportedRuntimeGameVersion = this.SupportedRuntimeGameVersion,
        SupportedGameVersion = this.SupportedGameVersion,
        RulesetGameVersion = this.SupportedGameVersion,
        RulesetContentFingerprint = this.RulesetContentFingerprint,
        Mods = [],
        UnsupportedMods = [],
        IsCompatible = false,
        CompatibilityReason = _reason
    };
    this.State.LastError = "runtime provenance unavailable: " + _reason;
    this.invalidate("runtime_incompatible");
    ::logError("[BB-Agent Capture] runtime provenance unavailable; capture disabled reason=" + _reason);
    return false;
};

capture._refreshRuntimeProvenance <- function()
{
    try
    {
        local runtimeGameVersion = ::GameInfo.getVersionNumber();
        local runtimeMods = this._runtimeModIdentities();
        local reason = null;

        if (runtimeGameVersion != this.SupportedRuntimeGameVersion)
            reason = "game_version_mismatch";
        else if (runtimeMods.Unsupported.len() != 0)
            reason = "unsupported_mod_stack";
        else if (!this._matchesExpectedProvenance(runtimeGameVersion, runtimeMods))
            reason = "explicit_provenance_mismatch";

        this.State.Provenance = {
            GameVersion = runtimeGameVersion,
            RuntimeSerializationVersion = ::Const.Serialization.Version,
            SupportedRuntimeGameVersion = this.SupportedRuntimeGameVersion,
            SupportedGameVersion = this.SupportedGameVersion,
            RulesetGameVersion = this.SupportedGameVersion,
            RulesetContentFingerprint = this.RulesetContentFingerprint,
            Mods = runtimeMods.Identities,
            UnsupportedMods = runtimeMods.Unsupported,
            IsCompatible = reason == null,
            CompatibilityReason = reason
        };

        if (reason != null)
        {
            this.State.LastError = "runtime incompatibility: " + reason;
            this.invalidate("runtime_incompatible");
            ::logError(
                "[BB-Agent Capture] incompatible runtime; capture disabled reason=" + reason
                + " game=" + runtimeGameVersion
            );
            return false;
        }

        this.State.LastError = null;
        return true;
    }
    catch (error)
    {
        return this._setProvenanceFailure("runtime_provenance_error");
    }
};

capture.isRuntimeCompatible <- function()
{
    return "IsCompatible" in this.State.Provenance
        && this.State.Provenance.IsCompatible;
};

// Optional stricter validation hook for #57. The expectation is persistent so
// battle initialization cannot silently erase an explicit incompatibility.
capture.configureProvenance = function(_gameVersion, _rulesetGameVersion, _contentFingerprint, _mods)
{
    if (_gameVersion == null || _gameVersion == "") throw "game version is required";
    if (_rulesetGameVersion == null || _rulesetGameVersion == "") throw "ruleset game version is required";
    if (_contentFingerprint == null || _contentFingerprint == "") throw "content fingerprint is required";
    if (_mods == null) throw "mod identities are required";

    local expectedMods = this._copyArray(_mods);
    expectedMods.sort();
    this.ExpectedProvenance = {
        GameVersion = _gameVersion,
        RulesetGameVersion = _rulesetGameVersion,
        RulesetContentFingerprint = _contentFingerprint,
        Mods = expectedMods
    };

    return this._refreshRuntimeProvenance();
};

capture._refreshRuntimeProvenance();
