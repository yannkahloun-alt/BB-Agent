local legal = ::BBAGENT_PlayerLegal;

// Battle Brothers exposes several player-facing whole-number getters through
// Math.floor/Math.round. In Squirrel those results can still have runtime type
// `float` (for example item.getCondition() returned float 48 in live 1.5.2.3).
// The canonical live wire deliberately rejects floats, so normalize only these
// source-proven whole-number fields at the PLAYER_LEGAL projection boundary.
// Fail closed if a future runtime ever returns a genuinely fractional value.
legal._exactWholeNumber <- function(_wrapper, _label)
{
    if (_wrapper == null || !("representation" in _wrapper)) return _wrapper;
    if (_wrapper.representation != "EXACT") return _wrapper;

    local value = _wrapper.value;
    local kind = typeof value;
    if (kind == "integer") return _wrapper;
    if (kind != "float") return _wrapper;

    local integerValue = value.tointeger();
    if (value != integerValue)
        throw "player-legal whole-number field is fractional: " + _label;
    _wrapper.value = integerValue;
    return _wrapper;
};

local originalOwnedResources = legal._ownedResources;
legal._ownedResources = function(_actor)
{
    local resources = originalOwnedResources.acall([this, _actor]);
    foreach (field in [
        "hit_points",
        "maximum_hit_points",
        "action_points",
        "maximum_action_points",
        "fatigue",
        "fatigue_capacity",
        "head_armor",
        "maximum_head_armor",
        "body_armor",
        "maximum_body_armor",
        "morale",
        "initiative"
    ])
    {
        resources[field] = this._exactWholeNumber(
            resources[field],
            "resources." + field
        );
    }
    return resources;
};

local originalItemState = legal._itemState;
legal._itemState = function(_actor, _item, _slot, _position)
{
    local item = originalItemState.acall([this, _actor, _item, _slot, _position]);
    item.condition = this._exactWholeNumber(item.condition, "equipment.condition");
    item.ammunition = this._exactWholeNumber(item.ammunition, "equipment.ammunition");
    return item;
};

local originalOwnedStats = legal._ownedStats;
legal._ownedStats = function(_actor)
{
    local stats = originalOwnedStats.acall([this, _actor]);
    foreach (stat in stats)
        stat.value = this._exactWholeNumber(
            stat.value,
            "tactical_stats." + stat.stat_id
        );
    return stats;
};

::logInfo(
    "[BB-Agent PLAYER_LEGAL] numeric_compat_loaded"
    + " whole_number_float_normalization=true fail_fractional=true"
);
