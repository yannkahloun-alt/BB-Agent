local sandbox = ::BBAGENT_CombatSandbox;

// Selected forensic fields are genuinely unique state, not duplicate runtime
// scaffolding. Give each nested entry its own state_field record/reflection
// budget rather than truncating the entire structure behind one field record.
local originalEnqueueStateField = sandbox._enqueueStateField;

sandbox._enqueueNestedFieldTable <- function(
    _ownerSection,
    _ownerKey,
    _fieldKey,
    _ordinal,
    _value,
    _nestedOwnerSection
)
{
    local count = 0;
    local truncated = false;
    local iterationError = null;
    try
    {
        foreach (key, child in _value)
        {
            if (count >= this.MaxReflectEntries)
            {
                truncated = true;
                break;
            }
            originalEnqueueStateField.acall([
                this,
                _nestedOwnerSection,
                _ownerKey,
                key,
                count,
                child
            ]);
            ++count;
        }
    }
    catch (error)
    {
        iterationError = error.tostring();
    }

    local summary = {
        __bb_nested_field_shards = true,
        runtime_type = typeof _value,
        nested_owner_section = _nestedOwnerSection,
        entry_count = count,
        truncated = truncated
    };
    if (iterationError != null) summary.iteration_error <- iterationError;
    return originalEnqueueStateField.acall([
        this,
        _ownerSection,
        _ownerKey,
        _fieldKey,
        _ordinal,
        summary
    ]);
};

sandbox._enqueueNestedFieldArray <- function(
    _ownerSection,
    _ownerKey,
    _fieldKey,
    _ordinal,
    _value,
    _nestedOwnerSection
)
{
    local limit = ::Math.min(_value.len(), this.MaxReflectEntries);
    for (local i = 0; i < limit; i = ++i)
    {
        originalEnqueueStateField.acall([
            this,
            _nestedOwnerSection,
            _ownerKey,
            i,
            i,
            _value[i]
        ]);
    }
    return originalEnqueueStateField.acall([
        this,
        _ownerSection,
        _ownerKey,
        _fieldKey,
        _ordinal,
        {
            __bb_nested_field_shards = true,
            runtime_type = "array",
            nested_owner_section = _nestedOwnerSection,
            original_length = _value.len(),
            entry_count = limit,
            truncated = _value.len() > limit
        }
    ]);
};

sandbox._enqueueStateField = function(
    _ownerSection,
    _ownerKey,
    _fieldKey,
    _ordinal,
    _value
)
{
    local keyText = null;
    try { keyText = _fieldKey.tostring(); } catch (_error) {}

    if (_ownerSection == "constant" && keyText == "Actor"
        && (typeof _value == "table" || typeof _value == "instance"))
    {
        return this._enqueueNestedFieldTable(
            _ownerSection,
            _ownerKey,
            _fieldKey,
            _ordinal,
            _value,
            "constant_actor_entry"
        );
    }

    if (_ownerSection == "tactical_state" && keyText == "StrategicProperties"
        && (typeof _value == "table" || typeof _value == "instance"))
    {
        return this._enqueueNestedFieldTable(
            _ownerSection,
            _ownerKey,
            _fieldKey,
            _ordinal,
            _value,
            "strategic_property"
        );
    }

    if (_ownerSection == "entity_manager_state" && keyText == "Strategies"
        && typeof _value == "array")
    {
        return this._enqueueNestedFieldArray(
            _ownerSection,
            _ownerKey,
            _fieldKey,
            _ordinal,
            _value,
            "entity_strategy"
        );
    }

    return originalEnqueueStateField.acall([
        this,
        _ownerSection,
        _ownerKey,
        _fieldKey,
        _ordinal,
        _value
    ]);
};

::logInfo(
    "[BB-Agent Combat Sandbox] nested_fields_loaded unique_hot_fields=true"
);
