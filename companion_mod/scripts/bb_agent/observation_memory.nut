local capture = ::BBAGENT_Capture;

capture._isPlayerLegalMemoryValue <- function(_value, _depth = 0)
{
    if (_depth > 32) return false;

    local kind = typeof _value;
    if (kind == "null" || kind == "bool" || kind == "integer" || kind == "float" || kind == "string")
        return true;

    if (kind == "array")
    {
        foreach (value in _value)
        {
            if (!this._isPlayerLegalMemoryValue(value, _depth + 1)) return false;
        }
        return true;
    }

    if (kind == "table")
    {
        foreach (key, value in _value)
        {
            if (typeof key != "string") return false;
            if (!this._isPlayerLegalMemoryValue(value, _depth + 1)) return false;
        }
        return true;
    }

    return false;
};

capture._copyPlayerLegalMemoryValue <- function(_value)
{
    local kind = typeof _value;
    if (kind == "array")
    {
        local copy = [];
        foreach (value in _value) copy.push(this._copyPlayerLegalMemoryValue(value));
        return copy;
    }

    if (kind == "table")
    {
        local copy = {};
        foreach (key, value in _value)
            copy[key] <- this._copyPlayerLegalMemoryValue(value);
        return copy;
    }

    return _value;
};

// Legal observation memory accepts only transport-safe projected data. Runtime
// instances/functions/weak references are rejected instead of being retained.
capture.rememberPlayerLegalFact = function(_key, _value, _round, _decision)
{
    if (typeof _key != "string" || _key == "") throw "observation-memory key is required";
    if (!this._isPlayerLegalMemoryValue(_value))
        throw "observation-memory value must be player-legal data";
    if (typeof _round != "integer" || _round < 0)
        throw "observation-memory round must be a non-negative integer";
    if (typeof _decision != "integer" || _decision < 0)
        throw "observation-memory decision must be a non-negative integer";

    this.State.ObservationMemory[_key] <- {
        Value = this._copyPlayerLegalMemoryValue(_value),
        ObservedRound = _round,
        ObservedDecision = _decision
    };
};

// Return a detached deep copy so callers cannot mutate the capture store through
// either the entry wrapper or nested player-legal value tables/arrays.
capture.getObservationMemory = function()
{
    local snapshot = {};
    foreach (key, fact in this.State.ObservationMemory)
    {
        snapshot[key] <- {
            Value = this._copyPlayerLegalMemoryValue(fact.Value),
            ObservedRound = fact.ObservedRound,
            ObservedDecision = fact.ObservedDecision
        };
    }
    return snapshot;
};
