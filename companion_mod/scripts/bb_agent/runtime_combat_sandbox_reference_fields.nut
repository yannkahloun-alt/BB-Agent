local sandbox = ::BBAGENT_CombatSandbox;

// Large skill/item container fields duplicate information already emitted as
// dedicated actor_skill / actor_item records. Preserve the field's existence and
// collection shape, but replace recursive runtime-object expansion with a bounded
// forensic reference summary. This improves fidelity reporting without dropping
// any individually captured skill/item state.
local originalEnqueueStateField = sandbox._enqueueStateField;
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
    "[BB-Agent Combat Sandbox] reference_fields_loaded skill_item_containers=true"
);
