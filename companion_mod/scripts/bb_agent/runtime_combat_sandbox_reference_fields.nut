local sandbox = ::BBAGENT_CombatSandbox;

// Large container fields can duplicate information already emitted as dedicated
// actor / actor_skill / actor_item / turn records. Preserve field existence,
// cardinality and actor identities while replacing recursive runtime-object
// expansion with bounded reference summaries.
local originalEnqueueStateField = sandbox._enqueueStateField;

sandbox._runtimeActorReferences <- function(_value)
{
    local references = [];
    local kind = typeof _value;
    if (kind != "array")
        return { runtime_type = kind, references = references };

    local limit = ::Math.min(_value.len(), this.MaxReflectEntries);
    for (local i = 0; i < limit; i = ++i)
    {
        local entry = _value[i];
        if (entry == null)
        {
            references.push(null);
            continue;
        }

        if (typeof entry == "array")
        {
            local group = [];
            local groupLimit = ::Math.min(entry.len(), this.MaxReflectEntries);
            for (local j = 0; j < groupLimit; j = ++j)
            {
                local actor = entry[j];
                local runtimeId = null;
                if (actor != null)
                {
                    try { runtimeId = actor.getID().tostring(); } catch (_error) {}
                }
                group.push(runtimeId);
            }
            references.push({
                runtime_type = "array",
                original_length = entry.len(),
                truncated = entry.len() > groupLimit,
                actor_runtime_ids = group
            });
            continue;
        }

        local runtimeId = null;
        try { runtimeId = entry.getID().tostring(); } catch (_error) {}
        references.push(runtimeId);
    }

    return {
        runtime_type = kind,
        original_length = _value.len(),
        truncated = _value.len() > limit,
        references = references
    };
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

    if (_ownerSection == "actor_skills_container" && keyText == "Skills")
    {
        local count = null;
        try { count = _value.len(); } catch (_error) {}
        return originalEnqueueStateField.acall([
            this,
            _ownerSection,
            _ownerKey,
            _fieldKey,
            _ordinal,
            {
                __bb_reference_collection = "actor_skill",
                owner_actor_id = _ownerKey,
                runtime_type = typeof _value,
                entry_count = count
            }
        ]);
    }

    if (_ownerSection == "actor_items_container" && keyText == "Items")
    {
        local slotCount = null;
        try { slotCount = _value.len(); } catch (_error) {}
        return originalEnqueueStateField.acall([
            this,
            _ownerSection,
            _ownerKey,
            _fieldKey,
            _ordinal,
            {
                __bb_reference_collection = "actor_item",
                owner_actor_id = _ownerKey,
                runtime_type = typeof _value,
                slot_count = slotCount
            }
        ]);
    }

    if (_ownerSection == "entity_manager_state" && keyText == "Instances")
    {
        local summary = this._runtimeActorReferences(_value);
        summary.__bb_reference_collection <- "actor_core";
        summary.collection_role <- "entity_manager_instances";
        return originalEnqueueStateField.acall([
            this,
            _ownerSection,
            _ownerKey,
            _fieldKey,
            _ordinal,
            summary
        ]);
    }

    if (_ownerSection == "turn_sequence_state"
        && (keyText == "CurrentEntities" || keyText == "AllEntities"))
    {
        local summary = this._runtimeActorReferences(_value);
        summary.__bb_reference_collection <- "actor_core";
        summary.collection_role <- keyText;
        return originalEnqueueStateField.acall([
            this,
            _ownerSection,
            _ownerKey,
            _fieldKey,
            _ordinal,
            summary
        ]);
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
    "[BB-Agent Combat Sandbox] reference_fields_loaded duplicate_runtime_collections=true"
);
