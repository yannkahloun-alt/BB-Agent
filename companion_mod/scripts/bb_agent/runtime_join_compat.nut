local capture = ::BBAGENT_Capture;
local wire = ::BBAGENT_Wire;
local liveExport = ::BBAGENT_LiveExport;

// Battle Brothers embeds Squirrel without an Array.join default delegate.
// Keep all string joining explicit and deterministic on the active live path.
local compat = ::BBAGENT_RuntimeJoinCompat <- {
    function joinStrings(_values, _separator)
    {
        local out = "";
        for (local i = 0; i < _values.len(); i = ++i)
        {
            if (i != 0) out += _separator;
            out += _values[i];
        }
        return out;
    }
};

capture._arrayToken = function(_prefix, _values)
{
    local parts = [];
    foreach (value in _values) parts.push(value.tostring());
    return _prefix + ":" + compat.joinStrings(parts, ",");
};

capture._actorToken = function(_actor)
{
    local tokens = [
        "actor=" + _actor.getID(),
        "faction=" + _actor.getFaction(),
        "alive=" + this._boolToken(_actor.isAlive()),
        "placed=" + this._boolToken(_actor.isPlacedOnMap()),
        this._tileToken(_actor),
        "hp=" + _actor.getHitpoints(),
        "hpmax=" + _actor.getHitpointsMax(),
        "armor_body=" + _actor.getArmor(::Const.BodyPart.Body),
        "armor_head=" + _actor.getArmor(::Const.BodyPart.Head),
        "ap=" + _actor.getActionPoints(),
        "fatigue=" + _actor.getFatigue(),
        "fatiguemax=" + _actor.getFatigueMax(),
        "morale=" + _actor.getMoraleState(),
        "waitspent=" + this._boolToken(_actor.isWaitActionSpent()),
        "turnstarted=" + this._boolToken(_actor.isTurnStarted()),
        "turndone=" + this._boolToken(_actor.isTurnDone()),
        "movement_type=" + _actor.m.CurrentMovementType,
        "level_ap=" + _actor.m.LevelActionPointCost,
        "level_fatigue=" + _actor.m.LevelFatigueCost,
        "max_traversible_levels=" + _actor.m.MaxTraversibleLevels,
        "uses_zoc=" + this._boolToken(_actor.m.IsUsingZoneOfControl),
        "exerts_zoc=" + this._boolToken(_actor.m.IsExertingZoneOfControl),
        this._arrayToken("movement_ap", _actor.m.ActionPointCosts),
        this._arrayToken("movement_fatigue", _actor.m.FatigueCosts)
    ];

    foreach (propertyToken in this._primitiveStateTokens("properties", _actor.getCurrentProperties()))
        tokens.push(propertyToken);
    foreach (skillToken in this._skillTokens(_actor)) tokens.push(skillToken);
    foreach (itemToken in this._itemTokens(_actor)) tokens.push(itemToken);
    tokens.sort();
    return compat.joinStrings(tokens, ",");
};

capture._sourceSignature = function(_inputs)
{
    return compat.joinStrings(_inputs, "\x1f");
};

capture._sanitizeDiagnosticError = function(_error)
{
    local errorText = _error == null ? "null" : _error.tostring();
    errorText = compat.joinStrings(split(errorText, "\r\n\t"), " ");
    if (errorText.len() > this.DiagnosticMaxErrorChars)
        errorText = errorText.slice(0, this.DiagnosticMaxErrorChars);
    return errorText;
};

wire.canonicalJson = function(_value)
{
    local kind = typeof _value;
    if (kind == "null") return "null";
    if (kind == "bool") return _value ? "true" : "false";
    if (kind == "integer") return _value.tostring();
    if (kind == "float") throw "canonical live JSON does not accept floats";
    if (kind == "string") return this._jsonEscape(_value);
    if (kind == "array")
    {
        local parts = [];
        foreach (child in _value) parts.push(this.canonicalJson(child));
        return "[" + compat.joinStrings(parts, ",") + "]";
    }
    if (kind == "table")
    {
        local keys = [];
        foreach (key, _child in _value)
        {
            if (typeof key != "string") throw "canonical JSON object keys must be strings";
            keys.push(key);
        }
        keys.sort();
        local parts = [];
        foreach (key in keys)
            parts.push(this._jsonEscape(key) + ":" + this.canonicalJson(_value[key]));
        return "{" + compat.joinStrings(parts, ",") + "}";
    }
    throw "unsupported canonical live JSON type: " + kind;
};

liveExport._sanitizeExportError = function(_error)
{
    local errorText = _error == null ? "null" : _error.tostring();
    errorText = compat.joinStrings(split(errorText, "\r\n\t"), " ");
    if (errorText.len() > this.DiagnosticMaxErrorChars)
        errorText = errorText.slice(0, this.DiagnosticMaxErrorChars);
    return errorText;
};
