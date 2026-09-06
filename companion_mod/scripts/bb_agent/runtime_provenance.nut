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

capture._refreshRuntimeProvenance <- function()
{
    local runtimeGameVersion = ::GameInfo.getVersionNumber();
    local runtimeMods = this._runtimeModIdentities();
    local reason = null;

    if (runtimeGameVersion != this.SupportedRuntimeGameVersion)
        reason = "game_version_mismatch";
    else if (runtimeMods.Unsupported.len() != 0)
        reason = "unsupported_mod_stack";

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
        ::logError(
            "[BB-Agent Capture] incompatible runtime; capture disabled reason=" + reason
            + " game=" + runtimeGameVersion
        );
        return false;
    }

    return true;
};

capture.isRuntimeCompatible <- function()
{
    return "IsCompatible" in this.State.Provenance
        && this.State.Provenance.IsCompatible;
};

// Optional stricter validation hook for #57. It may verify the exact expected
// runtime mod identities but cannot override the built-in supported-build gate.
capture.configureProvenance = function(_gameVersion, _rulesetGameVersion, _contentFingerprint, _mods)
{
    this._refreshRuntimeProvenance();

    local expectedMods = this._copyArray(_mods);
    expectedMods.sort();
    local configuredMatch = _gameVersion == this.State.Provenance.GameVersion
        && _rulesetGameVersion == this.SupportedGameVersion
        && _contentFingerprint == this.RulesetContentFingerprint
        && this._arraysEqual(expectedMods, this.State.Provenance.Mods);

    if (!configuredMatch)
    {
        this.State.Provenance.IsCompatible = false;
        this.State.Provenance.CompatibilityReason = "explicit_provenance_mismatch";
        this.State.LastError = "runtime incompatibility: explicit_provenance_mismatch";
        ::logError("[BB-Agent Capture] incompatible runtime; capture disabled reason=explicit_provenance_mismatch");
        return false;
    }

    return this.isRuntimeCompatible();
};

capture._refreshRuntimeProvenance();
