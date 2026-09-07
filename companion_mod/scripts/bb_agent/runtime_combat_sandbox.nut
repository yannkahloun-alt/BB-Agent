local wire = ::BBAGENT_Wire;
local capture = ::BBAGENT_Capture;
local legal = ::BBAGENT_PlayerLegal;
local affordances = ::BBAGENT_Affordances;
local oracle = ::BBAGENT_DebugOracle;

::BBAGENT_CombatSandbox <- {
    FramePrefix = "BBCOMBAT1",
    SchemaVersion = "bb-agent-combat-sandbox.v1",
    ChunkPayloadChars = 1200,
    MaxChunkLineBytes = 1500,
    MaxDecodedRecordBytes = 4194304,
    MaxEncodedRecordBytes = 6291456,
    MaxReflectDepth = 6,
    MaxReflectEntries = 512,
    LastAttemptKey = null,
    LastSnapshotKey = null,

    function _floatValue(_value)
    {
        return { __bb_type = "float", value = _value.tostring() };
    },

    function _omitted(_kind, _reason = null)
    {
        local ret = { __bb_type = _kind };
        if (_reason != null) ret.reason <- _reason;
        return ret;
    },

    function _reflect(_value, _depth = 0)
    {
        local kind = typeof _value;
        if (kind == "null" || kind == "bool" || kind == "integer" || kind == "string")
            return _value;
        if (kind == "float") return this._floatValue(_value);
        if (_depth >= this.MaxReflectDepth)
            return { __bb_type = kind, __bb_truncated = true, reason = "max_depth" };
        if (kind == "function" || kind == "nativeclosure" || kind == "class"
            || kind == "thread" || kind == "generator" || kind == "userdata"
            || kind == "weakref")
        {
            return this._omitted(kind);
        }
        if (kind == "instance" && _depth > 0)
            return this._omitted(kind, "nested_instance");

        if (kind == "array")
        {
            local items = [];
            local limit = ::Math.min(_value.len(), this.MaxReflectEntries);
            for (local i = 0; i < limit; i = ++i)
                items.push(this._reflect(_value[i], _depth + 1));
            if (_value.len() <= limit) return items;
            return {
                __bb_type = "array",
                __bb_truncated = true,
                original_length = _value.len(),
                items = items
            };
        }

        if (kind != "table" && kind != "instance")
            return this._omitted(kind, "unsupported");

        local ret = {};
        local count = 0;
        local truncated = false;
        try
        {
            foreach (key, child in _value)
            {
                if (count >= this.MaxReflectEntries)
                {
                    truncated = true;
                    break;
                }
                local keyKind = typeof key;
                local outKey = keyKind == "string"
                    ? key
                    : "__bb_key_" + keyKind + "_" + key.tostring();
                ret[outKey] <- this._reflect(child, _depth + 1);
                ++count;
            }
        }
        catch (error)
        {
            ret.__bb_iteration_error <- error.tostring();
        }
        if (truncated) ret.__bb_truncated <- true;
        if (kind == "instance") ret.__bb_type <- "instance";
        return ret;
    },

    function _tileID(_tile)
    {
        return legal.tileID(_tile);
    },

    function _actorID(_actor)
    {
        return legal.actorID(_actor);
    },

    function _tryActorName(_actor)
    {
        try { return _actor.getName(); }
        catch (_error) { return null; }
    },

    function _tryActorTitle(_actor)
    {
        try { return _actor.getTitle(); }
        catch (_error) { return null; }
    },

    function _tryEntityID(_entity)
    {
        if (_entity == null) return null;
        try { return _entity.getID().tostring(); }
        catch (_error) { return null; }
    },

    function _tryEntityType(_entity)
    {
        if (_entity == null) return null;
        try { return _entity.getType(); }
        catch (_error) { return null; }
    },

    function _skillRecord(_skill)
    {
        local record = {
            id = _skill.getID(),
            runtime_type = typeof _skill,
            state = this._reflect(_skill.m)
        };
        try { record.hidden <- _skill.isHidden(); } catch (_error) {}
        try { record.active <- _skill.isActive(); } catch (_error) {}
        try { record.disabled <- _skill.isDisabled(); } catch (_error) {}
        try { record.usable <- _skill.isUsable(); } catch (_error) {}
        try { record.affordable <- _skill.isAffordable(); } catch (_error) {}
        try { record.ap_cost <- _skill.getActionPointCost(); } catch (_error) {}
        try { record.fatigue_cost <- _skill.getFatigueCost(); } catch (_error) {}
        try { record.targeted <- _skill.isTargeted(); } catch (_error) {}
        try { record.targeting_actor <- _skill.isTargetingActor(); } catch (_error) {}
        try { record.aoe <- _skill.isAOE(); } catch (_error) {}
        try { record.ranged <- _skill.isRanged(); } catch (_error) {}
        try { record.min_range <- _skill.getMinRange(); } catch (_error) {}
        try { record.max_range <- _skill.getMaxRange(); } catch (_error) {}
        try { record.max_level_difference <- _skill.getMaxLevelDifference(); } catch (_error) {}
        return record;
    },

    function _itemRecord(_item)
    {
        local record = {
            id = _item.getID(),
            runtime_type = typeof _item,
            state = this._reflect(_item.m)
        };
        try { record.instance_id <- _item.getInstanceID().tostring(); } catch (_error) {}
        try { record.slot_type <- _item.getCurrentSlotType(); } catch (_error) {}
        try { record.condition <- _item.getCondition(); } catch (_error) {}
        try { record.condition_max <- _item.getConditionMax(); } catch (_error) {}
        try { record.ammo <- _item.getAmmo(); } catch (_error) {}
        try { record.ammo_max <- _item.getAmmoMax(); } catch (_error) {}
        try { record.ammo_cost <- _item.getAmmoCost(); } catch (_error) {}
        return record;
    },

    function _actorPayload(_actor, _active)
    {
        local placed = false;
        try { placed = _actor.isPlacedOnMap(); } catch (_error) {}
        local tileId = null;
        if (placed)
        {
            try { tileId = this._tileID(_actor.getTile()); } catch (_error) {}
        }

        local hidden = null;
        try { hidden = _actor.isHiddenToPlayer(); } catch (_error) {}
        local alliedWithActive = null;
        try { alliedWithActive = _active.isAlliedWith(_actor); } catch (_error) {}
        local faction = null;
        try { faction = _actor.getFaction(); } catch (_error) {}

        local skills = [];
        try
        {
            foreach (skill in _actor.getSkills().m.Skills)
            {
                if (skill == null || skill.isGarbage()) continue;
                skills.push(this._skillRecord(skill));
            }
        }
        catch (_error) {}
        skills.sort(@(a, b) a.id <=> b.id);

        local items = [];
        try
        {
            foreach (item in _actor.getItems().getAllItems())
            {
                if (item == null || item == -1 || item.isGarbage()) continue;
                items.push(this._itemRecord(item));
            }
        }
        catch (_error) {}
        items.sort(@(a, b) a.id <=> b.id);

        local aooSkill = null;
        try
        {
            local attack = _actor.getSkills().getAttackOfOpportunity();
            if (attack != null) aooSkill = attack.getID();
        }
        catch (_error) {}

        local aiState = null;
        try
        {
            local agent = _actor.getAIAgent();
            if (agent != null) aiState = this._reflect(agent.m);
        }
        catch (_error) {}

        local record = {
            runtime_id = _actor.getID().tostring(),
            canonical_actor_id = this._actorID(_actor),
            name = this._tryActorName(_actor),
            title = this._tryActorTitle(_actor),
            faction = faction,
            allied_with_active = alliedWithActive,
            is_player_controlled = _actor.isPlayerControlled(),
            hidden_to_player = hidden,
            alive = _actor.isAlive(),
            placed_on_map = placed,
            tile_id = tileId,
            type = this._tryEntityType(_actor),
            hitpoints = _actor.getHitpoints(),
            hitpoints_max = _actor.getHitpointsMax(),
            armor_head = _actor.getArmor(::Const.BodyPart.Head),
            armor_body = _actor.getArmor(::Const.BodyPart.Body),
            action_points = _actor.getActionPoints(),
            action_points_max = _actor.getActionPointsMax(),
            fatigue = _actor.getFatigue(),
            fatigue_max = _actor.getFatigueMax(),
            morale_state = _actor.getMoraleState(),
            initiative = _actor.getInitiative(),
            wait_spent = _actor.isWaitActionSpent(),
            turn_started = _actor.isTurnStarted(),
            turn_done = _actor.isTurnDone(),
            movement_ap_costs = this._reflect(_actor.getActionPointCosts()),
            movement_fatigue_costs = this._reflect(_actor.getFatigueCosts()),
            level_action_point_cost = _actor.getLevelActionPointCost(),
            level_fatigue_cost = _actor.getLevelFatigueCost(),
            max_traversible_levels = _actor.getMaxTraversibleLevels(),
            actor_state = this._reflect(_actor.m),
            current_properties = this._reflect(_actor.getCurrentProperties()),
            base_properties = this._reflect(_actor.getBaseProperties()),
            skills_container_state = this._reflect(_actor.getSkills().m),
            items_container_state = this._reflect(_actor.getItems().m),
            skills = skills,
            items = items,
            ai_state = aiState,
            attack_of_opportunity_skill_id = aooSkill
        };
        try { record.has_zone_of_control <- _actor.hasZoneOfControl(); } catch (_error) {}
        try { record.exerting_zone_of_control <- _actor.isExertingZoneOfControl(); } catch (_error) {}
        try { record.allied_factions <- this._reflect(_actor.getAlliedFactions()); } catch (_error) {}
        return record;
    },

    function _tilePayload(_tile)
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
                    runtime_kind = typeof entity
                };
                try { occupant.canonical_actor_id <- this._actorID(entity); } catch (_error) {}
                try { occupant.hidden_to_player <- entity.isHiddenToPlayer(); } catch (_error) {}
                try { occupant.faction <- entity.getFaction(); } catch (_error) {}
                try { occupant.state <- this._reflect(entity.m); } catch (_error) {}
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
            properties = this._reflect(_tile.Properties),
            occupant = occupant
        };
    },

    function _record(_section, _key, _payload)
    {
        return {
            section = _section,
            key = _key,
            schema_version = this.SchemaVersion,
            payload = _payload
        };
    },

    function _emitRecord(_raw, _section, _key, _payload)
    {
        local record = this._record(_section, _key, _payload);
        local raw = wire.canonicalJson(record);
        if (raw.len() > this.MaxDecodedRecordBytes)
            throw "combat sandbox record exceeds decoded payload bound";
        local digest = wire.sha256(raw);
        local encoded = wire.base64Url(raw);
        if (encoded.len() > this.MaxEncodedRecordBytes)
            throw "combat sandbox record exceeds encoded payload bound";

        local chunkCount = 0;
        for (local offset = 0; offset < encoded.len(); offset += this.ChunkPayloadChars)
            ++chunkCount;
        if (chunkCount == 0) chunkCount = 1;

        local index = 0;
        for (local offset = 0; offset < encoded.len(); offset += this.ChunkPayloadChars)
        {
            local end = ::Math.min(encoded.len(), offset + this.ChunkPayloadChars);
            local chunk = encoded.slice(offset, end);
            local line = this.FramePrefix + "|"
                + _raw.BattleSequence.tostring() + "|"
                + _raw.SourceGeneration.tostring() + "|"
                + _section + "|" + _key + "|"
                + index.tostring() + "|" + chunkCount.tostring() + "|"
                + raw.len().tostring() + "|" + digest + "|" + chunk;
            if (line.len() > this.MaxChunkLineBytes)
                throw "combat sandbox chunk exceeds log line bound";
            ::logInfo(line);
            ++index;
        }
        return _section + ":" + _key;
    },

    function _rawPayload(_raw)
    {
        return {
            capture_contract_version = _raw.CaptureContractVersion,
            provenance = this._reflect(_raw.Provenance),
            battle_sequence = _raw.BattleSequence,
            source_generation = _raw.SourceGeneration,
            validation_context = this._reflect(_raw.ValidationContext),
            raw_source_fingerprint_inputs = this._reflect(_raw.RawSourceFingerprintInputs),
            raw_source_fingerprint = wire.canonicalHash(_raw.RawSourceFingerprintInputs)
        };
    },

    function _turnPayload(_raw)
    {
        local order = [];
        foreach (index, actor in _raw.TurnSequenceBar.getCurrentEntities())
        {
            if (actor == null || actor.isNull()) continue;
            order.push({ index = index, runtime_id = actor.getID().tostring() });
        }
        return {
            round = _raw.TurnSequenceBar.getCurrentRound(),
            turn_position = _raw.TurnSequenceBar.getTurnPosition(),
            active_runtime_id = _raw.ActiveActor.getID().tostring(),
            current_entities = order,
            turn_sequence_state = this._reflect(_raw.TurnSequenceBar.m)
        };
    },

    function _constantsPayload(_active)
    {
        return {
            movement = this._reflect(::Const.Movement),
            direction = this._reflect(::Const.Direction),
            terrain_type = this._reflect(::Const.Tactical.TerrainType),
            active_player_navigator_settings = {
                action_point_costs = this._reflect(_active.getActionPointCosts()),
                fatigue_costs = this._reflect(_active.getFatigueCosts()),
                fatigue_cost_factor = this._reflect(::Const.Movement.FatigueCostFactor),
                action_point_cost_per_level = _active.getLevelActionPointCost(),
                fatigue_cost_per_level = _active.getLevelFatigueCost(),
                zone_of_control_cost = 4,
                allied_factions = this._reflect(_active.getAlliedFactions()),
                faction = _active.getFaction(),
                allow_zone_of_control_passing = true,
                is_player = true
            }
        };
    },

    function capture(_raw, _projection)
    {
        local key = _raw.BattleSequence.tostring() + ":" + _raw.SourceGeneration.tostring();
        if (this.LastAttemptKey == key) return;
        this.LastAttemptKey = key;

        ::logInfo(
            "[BB-Agent Combat Sandbox] capture_attempt battle="
            + _raw.BattleSequence.tostring()
            + " generation=" + _raw.SourceGeneration.tostring()
            + " oracle_enabled=" + oracle.Enabled.tostring()
        );
        if (!oracle.Enabled)
        {
            ::logInfo("[BB-Agent Combat Sandbox] skipped reason=oracle_disabled");
            return;
        }
        if (this.LastSnapshotKey == key) return;

        try
        {
            local expected = [];
            expected.push(this._emitRecord(_raw, "raw", "root", this._rawPayload(_raw)));
            expected.push(this._emitRecord(
                _raw,
                "tactical_state",
                "root",
                {
                    state = this._reflect(_raw.TacticalState.m),
                    runtime_type = typeof _raw.TacticalState
                }
            ));
            expected.push(this._emitRecord(_raw, "turn", "root", this._turnPayload(_raw)));
            expected.push(this._emitRecord(
                _raw,
                "entity_manager",
                "root",
                { state = this._reflect(_raw.EntityManager.m) }
            ));
            expected.push(this._emitRecord(
                _raw,
                "constants",
                "root",
                this._constantsPayload(_raw.ActiveActor)
            ));
            expected.push(this._emitRecord(
                _raw,
                "player_legal",
                "root",
                _projection.state
            ));
            expected.push(this._emitRecord(
                _raw,
                "observation_memory",
                "root",
                capture.getObservationMemory()
            ));

            local groups = _raw.EntityManager.getAllInstances();
            local actorCount = 0;
            foreach (group in groups)
            {
                foreach (actor in group)
                {
                    if (actor == null || actor.isNull()) continue;
                    local actorId = this._actorID(actor);
                    expected.push(this._emitRecord(
                        _raw,
                        "actor",
                        actorId,
                        this._actorPayload(actor, _raw.ActiveActor)
                    ));
                    ++actorCount;
                }
            }

            local tileCount = 0;
            local size = ::Tactical.getMapSize();
            for (local x = 0; x < size.X; x = ++x)
            {
                for (local y = 0; y < size.Y; y = ++y)
                {
                    if (!::Tactical.isValidTileSquare(x, y)) continue;
                    local tile = ::Tactical.getTileSquare(x, y);
                    local tileId = this._tileID(tile);
                    expected.push(this._emitRecord(
                        _raw,
                        "tile",
                        tileId,
                        this._tilePayload(tile)
                    ));
                    ++tileCount;
                }
            }

            expected.push("manifest:root");
            expected.sort();
            this._emitRecord(
                _raw,
                "manifest",
                "root",
                {
                    information_scope = "omniscient_debug",
                    scripts_revision = capture.SupportedScriptsRevision,
                    ruleset_content_fingerprint = capture.RulesetContentFingerprint,
                    companion_version = capture.State.Provenance.CompanionVersion,
                    battle_sequence = _raw.BattleSequence,
                    source_generation = _raw.SourceGeneration,
                    active_actor_id = this._actorID(_raw.ActiveActor),
                    actor_count = actorCount,
                    tile_count = tileCount,
                    expected_records = expected,
                    reflection = {
                        max_depth = this.MaxReflectDepth,
                        max_entries_per_container = this.MaxReflectEntries,
                        nested_instances = "type marker only",
                        unsupported_runtime_values = "type marker only"
                    }
                }
            );

            this.LastSnapshotKey = key;
            ::logInfo(
                "[BB-Agent Combat Sandbox] emitted battle="
                + _raw.BattleSequence.tostring()
                + " generation=" + _raw.SourceGeneration.tostring()
                + " actors=" + actorCount.tostring()
                + " tiles=" + tileCount.tostring()
                + " records=" + expected.len().tostring()
            );
        }
        catch (error)
        {
            ::logError("[BB-Agent Combat Sandbox] error=" + error.tostring());
        }
    }
};

::logInfo(
    "[BB-Agent Combat Sandbox] module_loaded schema="
    + ::BBAGENT_CombatSandbox.SchemaVersion
    + " oracle_enabled=" + oracle.Enabled.tostring()
);
