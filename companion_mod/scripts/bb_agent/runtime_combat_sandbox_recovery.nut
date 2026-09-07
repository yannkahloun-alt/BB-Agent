local sandbox = ::BBAGENT_CombatSandbox;

// Live oracle capture proved that a small set of otherwise-valid records can
// still fail at the final transport boundary: direct engine getters may return
// floats, and a deeply branching state field can exceed the per-record byte cap.
// Normalize only the already-constructed payload at emission, and retry only an
// oversized state field with a smaller reflection budget.
sandbox._sandboxJsonSafe <- function(_value)
{
    local kind = typeof _value;
    if (kind == "null" || kind == "bool" || kind == "integer" || kind == "string")
        return _value;
    if (kind == "float") return this._floatValue(_value);

    if (kind == "array")
    {
        local ret = [];
        foreach (value in _value) ret.push(this._sandboxJsonSafe(value));
        return ret;
    }

    if (kind == "table")
    {
        local ret = {};
        foreach (key, value in _value)
        {
            local keyKind = typeof key;
            local outKey = keyKind == "string"
                ? key
                : "__bb_key_" + keyKind + "_" + key.tostring();
            ret[outKey] <- this._sandboxJsonSafe(value);
        }
        return ret;
    }

    return this._omitted(kind, "non_json_payload_value");
};

local boundedEmitRecord = sandbox._emitRecord;
sandbox._emitRecord = function(_raw, _section, _key, _payload)
{
    return boundedEmitRecord.acall([
        this,
        _raw,
        _section,
        _key,
        this._sandboxJsonSafe(_payload)
    ]);
};

sandbox._sandboxReflectWithNodeBudget <- function(_value, _nodeBudget)
{
    local oldBudget = this.MaxReflectNodes;
    local oldActive = this.ReflectBudgetActive;
    local oldRemaining = this.ReflectBudgetRemaining;
    this.MaxReflectNodes = _nodeBudget;
    this.ReflectBudgetActive = false;
    this.ReflectBudgetRemaining = 0;

    local ret = null;
    try
    {
        ret = this._reflect(_value);
    }
    catch (error)
    {
        this.MaxReflectNodes = oldBudget;
        this.ReflectBudgetActive = oldActive;
        this.ReflectBudgetRemaining = oldRemaining;
        throw error;
    }

    this.MaxReflectNodes = oldBudget;
    this.ReflectBudgetActive = oldActive;
    this.ReflectBudgetRemaining = oldRemaining;
    return ret;
};

local boundedProcessJob = sandbox._processJob;
sandbox._processJob = function(_job)
{
    if (_job.kind != "state_field")
        return boundedProcessJob.acall([this, _job]);

    local lastError = null;
    foreach (nodeBudget in [2048, 512, 128])
    {
        local payload = {
            owner_section = _job.extra.owner_section,
            owner_key = _job.extra.owner_key,
            field_key_kind = _job.extra.field_key_kind,
            field_key_text = _job.extra.field_key_text,
            ordinal = _job.extra.ordinal,
            reflection_node_budget = nodeBudget,
            value = this._sandboxReflectWithNodeBudget(_job.target, nodeBudget)
        };
        try
        {
            this._emitRecord(this.State.raw, _job.section, _job.key, payload);
            return;
        }
        catch (error)
        {
            local message = error.tostring();
            lastError = error;
            if (message != "combat sandbox record exceeds decoded payload bound")
                throw error;
        }
    }

    throw lastError;
};

::logInfo(
    "[BB-Agent Combat Sandbox] recovery_loaded float_safe=true"
    + " adaptive_state_field_budget=true"
);
