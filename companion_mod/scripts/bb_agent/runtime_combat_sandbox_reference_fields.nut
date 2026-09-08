local sandbox = ::BBAGENT_CombatSandbox;
local legal = ::BBAGENT_PlayerLegal;

// Large container fields can duplicate information already emitted as dedicated
// actor / actor_skill / actor_item / turn records. Preserve field existence,
// cardinality and actor identities while replacing recursive runtime-object
// expansion with bounded reference summaries. UI scaffolding is summarized
// explicitly rather than recursively expanded into unrelated object graphs.
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

sandbox._runtimeScaffoldingSummary <- function(_role, _value)
{
    local summary = {
        __bb_runtime_scaffolding = true,
        role = _role,
        runtime_type = typeof _value,
        recursively_expanded = false
    };
    try { summary.class_name <- _value.ClassName; } catch (_error) {}
    try { summary.instance_name <- _value.InstanceName; } catch (_error) {}
    return summary;
};

sandbox._runtimeValueSummary <- function(_role, _value)
{
    local summary = {
        __bb_runtime_value_summary = true,
        role = _role,
        runtime_type = typeof _value,
        recursively_expanded = false
    };
    try { summary.value_text <- _value.tostring(); } catch (_error) {}
    return summary;
};

sandbox._actorBackReference <- function(_ownerKey, _role, _value)
{
    local summary = {
        __bb_reference_collection = "actor_core",
        collection_role = _role,
        owner_actor_id = _ownerKey,
        runtime_type = typeof _value
    };
    try { summary.actor_runtime_id <- _value.getID().tostring(); } catch (_error) {}
    return summary;
};

sandbox._backgroundReference <- function(_ownerKey, _value)
{
    local summary = {
        __bb_reference_collection = "actor_skill",
        collection_role = "background",
        owner_actor_id = _ownerKey,
        runtime_type = typeof _value
    };
    try { summary.skill_id <- _value.getID(); } catch (_error) {}
    return summary;
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

    if ((_ownerSection == "actor_skills_container"
            || _ownerSection == "actor_items_container")
        && keyText == "Actor")
    {
        return originalEnqueueStateField.acall([
            this,
            _ownerSection,
            _ownerKey,
            _fieldKey,
            _ordinal,
            this._actorBackReference(_ownerKey, _ownerSection, _value)
        ]);
    }

    if ((_ownerSection == "actor_state"
            || _ownerSection == "tile_occupant_state")
        && keyText == "Background")
    {
        return originalEnqueueStateField.acall([
            this,
            _ownerSection,
            _ownerKey,
            _fieldKey,
            _ordinal,
            this._backgroundReference(_ownerKey, _value)
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

    if (_ownerSection == "tactical_state" && keyText == "Factions")
    {
        local summary = this._runtimeScaffoldingSummary(
            "entity_manager_alias",
            _value
        );
        summary.__bb_reference_collection <- "entity_manager";
        return originalEnqueueStateField.acall([
            this,
            _ownerSection,
            _ownerKey,
            _fieldKey,
            _ordinal,
            summary
        ]);
    }

    if (_ownerSection == "tactical_state"
        && (keyText == "TacticalScreen" || keyText == "MenuStack"))
    {
        return originalEnqueueStateField.acall([
            this,
            _ownerSection,
            _ownerKey,
            _fieldKey,
            _ordinal,
            this._runtimeScaffoldingSummary(keyText, _value)
        ]);
    }

    if (_ownerSection == "tactical_global"
        && (keyText == "TopbarRoundInformation"
            || keyText == "TurnSequenceBar"
            || keyText == "CameraDirector"
            || keyText == "CombatResultLoot"
            || keyText == "Entities"
            || keyText == "EventLog"
            || keyText == "TopbarOptions"
            || keyText == "OrientationOverlay"
            || keyText == "State"))
    {
        return originalEnqueueStateField.acall([
            this,
            _ownerSection,
            _ownerKey,
            _fieldKey,
            _ordinal,
            this._runtimeScaffoldingSummary(keyText, _value)
        ]);
    }

    if (_ownerSection == "strategic_property" && keyText == "Tile")
    {
        local tileId = null;
        try { tileId = legal.tileID(_value); } catch (_error) {}
        return originalEnqueueStateField.acall([
            this,
            _ownerSection,
            _ownerKey,
            _fieldKey,
            _ordinal,
            {
                __bb_reference_collection = "tile",
                collection_role = "strategic_property_tile",
                tile_id = tileId,
                runtime_type = typeof _value
            }
        ]);
    }

    if (_ownerSection == "constant"
        && (keyText == "EnemySelectionColor"
            || keyText == "ShakeEffectArmorHitHighlight"
            || keyText == "ShakeEffectSplitShieldColor"
            || keyText == "ShakeEffectArmorHitColor"
            || keyText == "ShakeEffectHitpointsHitHighlight"
            || keyText == "ShakeEffectHitpointsHitColor"
            || keyText == "HumanCorpseOffset"
            || keyText == "ShakeEffectSplitShieldHighlight"))
    {
        return originalEnqueueStateField.acall([
            this,
            _ownerSection,
            _ownerKey,
            _fieldKey,
            _ordinal,
            this._runtimeValueSummary(keyText, _value)
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
