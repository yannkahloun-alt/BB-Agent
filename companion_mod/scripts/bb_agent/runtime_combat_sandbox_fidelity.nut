local sandbox = ::BBAGENT_CombatSandbox;

// Preserve broad forensic state without allowing one large actor/global/container
// reflection to consume an entire logical record. Heavy records remain as small
// parent summaries; each top-level field is emitted independently and therefore
// gets its own reflection budget, record-size cap, digest and transport chunks.

sandbox._stateFieldKeyMeta <- function(_key)
{
    local kind = typeof _key;
    local text = null;
    if (kind == "null") text = "null";
    else
    {
        try { text = _key.tostring(); }
        catch (_error) { text = "<unprintable>"; }
    }
    return { field_key_kind = kind, field_key_text = text };
};

sandbox._enqueueStateField <- function(
    _ownerSection,
    _ownerKey,
    _fieldKey,
    _ordinal,
    _value
)
{
    local meta = this._stateFieldKeyMeta(_fieldKey);
    local recordKey = this.State.field_record_index.tostring();
    ++this.State.field_record_index;
    this._enqueue(
        "state_field",
        "state_field",
        recordKey,
        _value,
        {
            owner_section = _ownerSection,
            owner_key = _ownerKey,
            field_key_kind = meta.field_key_kind,
            field_key_text = meta.field_key_text,
            ordinal = _ordinal
        }
    );
};

sandbox._shardTopLevel <- function(_ownerSection, _ownerKey, _container)
{
    local kind = typeof _container;
    local count = 0;
    local truncated = false;
    local iterationError = null;

    if (kind == "array")
    {
        local limit = ::Math.min(_container.len(), this.MaxReflectEntries);
        for (local i = 0; i < limit; i = ++i)
        {
            this._enqueueStateField(
                _ownerSection,
                _ownerKey,
                i,
                i,
                _container[i]
            );
            ++count;
        }
        truncated = _container.len() > limit;
    }
    else if (kind == "table" || kind == "instance")
    {
        try
        {
            foreach (key, value in _container)
            {
                if (count >= this.MaxReflectEntries)
                {
                    truncated = true;
                    break;
                }
                this._enqueueStateField(
                    _ownerSection,
                    _ownerKey,
                    key,
                    count,
                    value
                );
                ++count;
            }
        }
        catch (error)
        {
            iterationError = error.tostring();
        }
    }
    else if (kind != "null")
    {
        this._enqueueStateField(
            _ownerSection,
            _ownerKey,
            "value",
            0,
            _container
        );
        count = 1;
    }

    local parent = {
        capture_mode = "top_level_field_shards",
        field_section = "state_field",
        owner_section = _ownerSection,
        owner_key = _ownerKey,
        runtime_type = kind,
        field_count = count,
        truncated = truncated
    };
    if (iterationError != null) parent.iteration_error <- iterationError;
    if (kind == "array") parent.original_length <- _container.len();
    return parent;
};

sandbox._constantRaw <- function(_key)
{
    if (_key == "movement") return ::Const.Movement;
    if (_key == "direction") return ::Const.Direction;
    if (_key == "tactical") return ::Const.Tactical;
    if (_key == "combat")
    {
        try { return ::Const.Combat; }
        catch (_error) { return null; }
    }
    if (_key == "items") return ::Const.Items;
    if (_key == "skill_type") return ::Const.SkillType;
    if (_key == "item_slot") return ::Const.ItemSlot;
    if (_key == "body_part") return ::Const.BodyPart;
    if (_key == "morale_state") return ::Const.MoraleState;
    return null;
};

sandbox._skillCoreRecord <- function(_skill)
{
    local record = {
        id = _skill.getID(),
        runtime_type = typeof _skill
    };
    try { record.hidden <- _skill.isHidden(); } catch (_error) {}
    try { record.active <- _skill.isActive(); } catch (_error) {}
    try { record.disabled <- _skill.isDisabled(); } catch (_error) {}
    try { record.usable <- _skill.isUsable(); } catch (_error) {}
    try { record.affordable <- _skill.isAffordable(); } catch (_error) {}
    try { record.ap_cost <- this._reflect(_skill.getActionPointCost()); } catch (_error) {}
    try { record.fatigue_cost <- this._reflect(_skill.getFatigueCost()); } catch (_error) {}
    try { record.targeted <- _skill.isTargeted(); } catch (_error) {}
    try { record.targeting_actor <- _skill.isTargetingActor(); } catch (_error) {}
    try { record.aoe <- _skill.isAOE(); } catch (_error) {}
    try { record.ranged <- _skill.isRanged(); } catch (_error) {}
    try { record.min_range <- this._reflect(_skill.getMinRange()); } catch (_error) {}
    try { record.max_range <- this._reflect(_skill.getMaxRange()); } catch (_error) {}
    try { record.max_level_difference <- this._reflect(_skill.getMaxLevelDifference()); } catch (_error) {}
    return record;
};

sandbox._itemCoreRecord <- function(_item)
{
    local record = {
        id = _item.getID(),
        runtime_type = typeof _item
    };
    try { record.instance_id <- _item.getInstanceID().tostring(); } catch (_error) {}
    try { record.slot_type <- _item.getCurrentSlotType(); } catch (_error) {}
    try { record.condition <- _item.getCondition(); } catch (_error) {}
    try { record.condition_max <- _item.getConditionMax(); } catch (_error) {}
    try { record.ammo <- _item.getAmmo(); } catch (_error) {}
    try { record.ammo_max <- _item.getAmmoMax(); } catch (_error) {}
    try { record.ammo_cost <- _item.getAmmoCost(); } catch (_error) {}
    return record;
};

sandbox._turnCorePayload <- function(_raw)
{
    local order = [];
    foreach (index, actor in _raw.TurnSequenceBar.getCurrentEntities())
    {
        if (actor == null) continue;
        order.push({ index = index, runtime_id = actor.getID().tostring() });
    }
    return {
        round = _raw.TurnSequenceBar.getCurrentRound(),
        turn_position = _raw.TurnSequenceBar.getTurnPosition(),
        active_runtime_id = _raw.ActiveActor.getID().tostring(),
        current_entities = order,
        turn_sequence_state_sharded = true
    };
};

sandbox._tileCorePayload <- function(_tile)
{
    local neighbors = [];
    foreach (direction in [
        ::Const.Direction.N,
        ::Const.Direction.NE,
        ::Const.Direction.SE,
        ::Const.Direction.S,
        ::Const.Direction.SW,
        ::Const.Direction.NW
    ])
    {
        if (!_tile.hasNextTile(direction))
        {
            neighbors.push(null);
            continue;
        }
        local next = _tile.getNextTile(direction);
        neighbors.push(next == null ? null : this._tileID(next));
    }

    local occupant = null;
    if (!_tile.IsEmpty)
    {
        local entity = null;
        try { entity = _tile.getEntity(); } catch (_error) {}
        if (entity != null)
        {
            occupant = {
                runtime_id = this._tryEntityID(entity),
                type = this._tryEntityType(entity),
                runtime_kind = typeof entity,
                state_sharded = true
            };
            try { occupant.canonical_actor_id <- this._actorID(entity); } catch (_error) {}
            try { occupant.hidden_to_player <- entity.isHiddenToPlayer(); } catch (_error) {}
            try { occupant.faction <- entity.getFaction(); } catch (_error) {}
        }
    }

    return {
        tile_id = this._tileID(_tile),
        x = _tile.SquareCoords.X,
        y = _tile.SquareCoords.Y,
        level = _tile.Level,
        terrain_type = _tile.Type,
        terrain_subtype = _tile.Subtype,
        is_empty = _tile.IsEmpty,
        visible_for_player = _tile.IsVisibleForPlayer,
        discovered = _tile.IsDiscovered,
        neighbor_ids = neighbors,
        properties_sharded = true,
        occupant = occupant
    };
};

local originalProcessJob = sandbox._processJob;
sandbox._processJob = function(_job)
{
    local raw = this.State.raw;
    local kind = _job.kind;

    if (kind == "state_field")
    {
        local payload = {
            owner_section = _job.extra.owner_section,
            owner_key = _job.extra.owner_key,
            field_key_kind = _job.extra.field_key_kind,
            field_key_text = _job.extra.field_key_text,
            ordinal = _job.extra.ordinal,
            value = this._reflect(_job.target)
        };
        this._emitRecord(raw, _job.section, _job.key, payload);
        return;
    }

    local parent = null;
    if (kind == "tactical_state")
    {
        parent = this._shardTopLevel("tactical_state", _job.key, raw.TacticalState.m);
    }
    else if (kind == "turn")
    {
        parent = this._turnCorePayload(raw);
        parent.turn_sequence_state <- this._shardTopLevel(
            "turn_sequence_state",
            _job.key,
            raw.TurnSequenceBar.m
        );
    }
    else if (kind == "entity_manager")
    {
        parent = {
            state = this._shardTopLevel(
                "entity_manager_state",
                _job.key,
                raw.EntityManager.m
            ),
            runtime = this._shardTopLevel(
                "entity_manager_runtime",
                _job.key,
                raw.EntityManager
            )
        };
    }
    else if (kind == "tactical_global")
    {
        parent = this._shardTopLevel("tactical_global", _job.key, ::Tactical);
    }
    else if (kind == "navigator")
    {
        parent = this._shardTopLevel("navigator", _job.key, raw.Navigator);
    }
    else if (kind == "constant")
    {
        parent = this._shardTopLevel(
            "constant",
            _job.key,
            this._constantRaw(_job.key)
        );
    }
    else if (kind == "actor_state")
    {
        parent = this._shardTopLevel("actor_state", _job.key, _job.target.m);
    }
    else if (kind == "actor_properties")
    {
        parent = {
            current = this._shardTopLevel(
                "actor_current_properties",
                _job.key,
                _job.target.getCurrentProperties()
            ),
            base_properties = this._shardTopLevel(
                "actor_base_properties",
                _job.key,
                _job.target.getBaseProperties()
            )
        };
    }
    else if (kind == "actor_skills_container")
    {
        parent = this._shardTopLevel(
            "actor_skills_container",
            _job.key,
            _job.target.getSkills().m
        );
    }
    else if (kind == "actor_items_container")
    {
        parent = this._shardTopLevel(
            "actor_items_container",
            _job.key,
            _job.target.getItems().m
        );
    }
    else if (kind == "actor_ai")
    {
        local agent = null;
        try { agent = _job.target.getAIAgent(); } catch (_error) {}
        parent = this._shardTopLevel(
            "actor_ai",
            _job.key,
            agent == null ? null : agent.m
        );
    }
    else if (kind == "actor_skill")
    {
        local skill = this._skillCoreRecord(_job.target);
        parent = {
            actor_id = _job.extra,
            skill = skill,
            state = this._shardTopLevel(
                "actor_skill_state",
                _job.key,
                _job.target.m
            )
        };
    }
    else if (kind == "actor_item")
    {
        local item = this._itemCoreRecord(_job.target);
        parent = {
            actor_id = _job.extra,
            item = item,
            state = this._shardTopLevel(
                "actor_item_state",
                _job.key,
                _job.target.m
            )
        };
    }
    else if (kind == "tile")
    {
        parent = this._tileCorePayload(_job.target);
        parent.property_fields <- this._shardTopLevel(
            "tile_properties",
            _job.key,
            _job.target.Properties
        );
        if (!_job.target.IsEmpty && parent.occupant != null)
        {
            local entity = null;
            try { entity = _job.target.getEntity(); } catch (_error) {}
            if (entity != null)
            {
                try
                {
                    parent.occupant.state_fields <- this._shardTopLevel(
                        "tile_occupant_state",
                        _job.key,
                        entity.m
                    );
                }
                catch (_error) {}
            }
        }
    }
    else
    {
        return originalProcessJob.acall([this, _job]);
    }

    this._emitRecord(raw, _job.section, _job.key, parent);
};

local originalBegin = sandbox.begin;
sandbox.begin = function(_raw)
{
    originalBegin.acall([this, _raw]);
    if (this.State != null && !("field_record_index" in this.State))
        this.State.field_record_index <- 0;
};

::logInfo(
    "[BB-Agent Combat Sandbox] fidelity_loaded top_level_field_shards=true"
);
