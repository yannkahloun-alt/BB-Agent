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
    RecordsPerPump = 1,
    ManifestShardSize = 64,
    State = null,
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
        {
            local marker = this._omitted(kind, "nested_instance");
            try { marker.runtime_id <- _value.getID().tostring(); } catch (_error) {}
            try { marker.state <- this._reflect(_value.m, _depth + 1); } catch (_error) {}
            return marker;
        }

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

    function _enqueue(
        _kind,
        _section = null,
        _key = null,
        _target = null,
        _extra = null,
        _expected = true
    )
    {
        if (this.State == null) return;
        this.State.jobs.push({
            kind = _kind,
            section = _section,
            key = _key,
            target = _target,
            extra = _extra
        });
        if (_expected && _section != null && _key != null)
            this.State.expected_records.push(_section + ":" + _key);
    },

    function _actorCorePayload(_actor, _active)
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
        local aooSkill = null;
        try
        {
            local attack = _actor.getSkills().getAttackOfOpportunity();
            if (attack != null) aooSkill = attack.getID();
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
            attack_of_opportunity_skill_id = aooSkill
        };
        try { record.has_zone_of_control <- _actor.hasZoneOfControl(); } catch (_error) {}
        try { record.exerting_zone_of_control <- _actor.isExertingZoneOfControl(); } catch (_error) {}
        try { record.allied_factions <- this._reflect(_actor.getAlliedFactions()); } catch (_error) {}
        return record;
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

    function _rawMetaPayload(_raw)
    {
        return {
            capture_contract_version = _raw.CaptureContractVersion,
            provenance = this._reflect(_raw.Provenance),
            battle_sequence = _raw.BattleSequence,
            source_generation = _raw.SourceGeneration,
            validation_context = this._reflect(_raw.ValidationContext),
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

    function _constantPayload(_key)
    {
        if (_key == "movement") return this._reflect(::Const.Movement);
        if (_key == "direction") return this._reflect(::Const.Direction);
        if (_key == "tactical") return this._reflect(::Const.Tactical);
        if (_key == "combat")
        {
            try { return this._reflect(::Const.Combat); }
            catch (_error) { return this._omitted("table", "Const.Combat unavailable"); }
        }
        if (_key == "items") return this._reflect(::Const.Items);
        if (_key == "skill_type") return this._reflect(::Const.SkillType);
        if (_key == "item_slot") return this._reflect(::Const.ItemSlot);
        if (_key == "body_part") return this._reflect(::Const.BodyPart);
        if (_key == "morale_state") return this._reflect(::Const.MoraleState);
        return this._omitted("table", "unknown constant section");
    },

    function _activeNavigatorSettingsPayload(_active)
    {
        local properties = _active.getCurrentProperties();
        return {
            action_point_costs = this._reflect(_active.getActionPointCosts()),
            fatigue_costs = this._reflect(_active.getFatigueCosts()),
            fatigue_cost_factor = this._reflect(::Const.Movement.FatigueCostFactor),
            action_point_cost_per_level = _active.getLevelActionPointCost(),
            fatigue_cost_per_level = _active.getLevelFatigueCost(),
            zone_of_control_cost = 4,
            allied_factions = this._reflect(_active.getAlliedFactions()),
            faction = _active.getFaction(),
            allow_zone_of_control_passing = true,
            is_player = true,
            fatigue_effect_mult = this._reflect(properties.FatigueEffectMult),
            is_rooted = properties.IsRooted,
            is_stunned = properties.IsStunned,
            is_immune_to_zone_of_control = properties.IsImmuneToZoneOfControl
        };
    },

    function _enqueueActors(_raw)
    {
        local groups = _raw.EntityManager.getAllInstances();
        foreach (group in groups)
        {
            foreach (actor in group)
            {
                if (actor == null || actor.isNull()) continue;
                local actorId = this._actorID(actor);
                ++this.State.actor_count;
                this._enqueue("actor_core", "actor_core", actorId, actor);
                this._enqueue("actor_state", "actor_state", actorId, actor);
                this._enqueue("actor_properties", "actor_properties", actorId, actor);
                this._enqueue("actor_skills_container", "actor_skills_container", actorId, actor);
                this._enqueue("actor_items_container", "actor_items_container", actorId, actor);
                this._enqueue("actor_ai", "actor_ai", actorId, actor);

                try
                {
                    local skillIndex = 0;
                    foreach (skill in actor.getSkills().m.Skills)
                    {
                        if (skill == null || skill.isGarbage()) continue;
                        local skillKey = actorId + ":" + skillIndex.tostring();
                        this._enqueue("actor_skill", "actor_skill", skillKey, skill, actorId);
                        ++skillIndex;
                    }
                }
                catch (_error) {}

                try
                {
                    local itemIndex = 0;
                    foreach (item in actor.getItems().getAllItems())
                    {
                        if (item == null || item == -1 || item.isGarbage()) continue;
                        local itemKey = actorId + ":" + itemIndex.tostring();
                        this._enqueue("actor_item", "actor_item", itemKey, item, actorId);
                        ++itemIndex;
                    }
                }
                catch (_error) {}
            }
        }
    },

    function _enqueueTiles()
    {
        local size = ::Tactical.getMapSize();
        for (local x = 0; x < size.X; x = ++x)
        {
            for (local y = 0; y < size.Y; y = ++y)
            {
                if (!::Tactical.isValidTileSquare(x, y)) continue;
                local tile = ::Tactical.getTileSquare(x, y);
                local tileId = this._tileID(tile);
                this._enqueue("tile", "tile", tileId, tile);
                ++this.State.tile_count;
            }
        }
    },

    function _enqueueProjectionRecords(_projection)
    {
        local meta = clone _projection.state;
        delete meta.tiles;
        delete meta.combatants;
        delete meta.action_affordances;
        this._enqueue("player_legal_meta", "player_legal_meta", "root", meta);

        foreach (tile in _projection.state.tiles)
            this._enqueue("player_legal_tile", "player_legal_tile", tile.tile_id, tile);
        foreach (actor in _projection.state.combatants)
            this._enqueue("player_legal_actor", "player_legal_actor", actor.actor_id, actor);

        local memoryIndex = 0;
        foreach (key, fact in capture.getObservationMemory())
        {
            this._enqueue(
                "observation_memory",
                "observation_memory",
                memoryIndex.tostring(),
                fact,
                key
            );
            ++memoryIndex;
        }
    },

    function _enqueueManifestJobs()
    {
        if (this.State == null || this.State.finalizing) return;
        this.State.finalizing = true;
        local expected = clone this.State.expected_records;
        expected.sort();
        local shardIndex = 0;
        for (local offset = 0; offset < expected.len(); offset += this.ManifestShardSize)
        {
            local records = [];
            local end = ::Math.min(expected.len(), offset + this.ManifestShardSize);
            for (local i = offset; i < end; i = ++i) records.push(expected[i]);
            local key = shardIndex.tostring();
            local recordId = "manifest_expected:" + key;
            this.State.expected_shards.push(recordId);
            this._enqueue(
                "manifest_expected",
                "manifest_expected",
                key,
                { records = records },
                null,
                false
            );
            ++shardIndex;
        }
        this._enqueue("manifest_root", "manifest", "root", null, null, false);
    },

    function _manifestPayload()
    {
        return {
            information_scope = "omniscient_debug",
            scripts_revision = capture.SupportedScriptsRevision,
            ruleset_content_fingerprint = capture.RulesetContentFingerprint,
            companion_version = capture.State.Provenance.CompanionVersion,
            battle_sequence = this.State.battle_sequence,
            source_generation = this.State.source_generation,
            active_actor_id = this._actorID(this.State.raw.ActiveActor),
            actor_count = this.State.actor_count,
            tile_count = this.State.tile_count,
            expected_record_count = this.State.expected_records.len(),
            expected_shards = clone this.State.expected_shards,
            reflection = {
                max_depth = this.MaxReflectDepth,
                max_entries_per_container = this.MaxReflectEntries,
                nested_instances = "bounded m-state marker",
                unsupported_runtime_values = "type marker only"
            },
            staging = {
                records_per_update = this.RecordsPerPump,
                manifest_shard_size = this.ManifestShardSize
            }
        };
    },

    function _emitJobError(_job, _error)
    {
        if (_job.section == null || _job.key == null) return;
        this._emitRecord(
            this.State.raw,
            _job.section,
            _job.key,
            {
                __capture_error = _error.tostring(),
                job_kind = _job.kind
            }
        );
    },

    function _processJob(_job)
    {
        local raw = this.State.raw;
        if (_job.kind == "player_legal_build")
        {
            try
            {
                local projection = ::BBAGENT_PlayerLegal.build(raw);
                this.State.player_legal_projection = projection;
                this._enqueueProjectionRecords(projection);
            }
            catch (error)
            {
                this._enqueue(
                    "player_legal_meta",
                    "player_legal_meta",
                    "root",
                    { __capture_error = error.tostring(), job_kind = _job.kind }
                );
                local memoryIndex = 0;
                foreach (key, fact in capture.getObservationMemory())
                {
                    this._enqueue(
                        "observation_memory",
                        "observation_memory",
                        memoryIndex.tostring(),
                        fact,
                        key
                    );
                    ++memoryIndex;
                }
            }
            return;
        }

        local payload = null;
        if (_job.kind == "raw_meta") payload = this._rawMetaPayload(raw);
        else if (_job.kind == "raw_fingerprint_input")
        {
            payload = {
                index = _job.extra,
                value = this._reflect(_job.target)
            };
        }
        else if (_job.kind == "tactical_state")
        {
            payload = {
                state = this._reflect(raw.TacticalState.m),
                runtime_type = typeof raw.TacticalState
            };
        }
        else if (_job.kind == "turn") payload = this._turnPayload(raw);
        else if (_job.kind == "entity_manager")
        {
            payload = {
                state = this._reflect(raw.EntityManager.m),
                runtime = this._reflect(raw.EntityManager)
            };
        }
        else if (_job.kind == "tactical_global") payload = this._reflect(::Tactical);
        else if (_job.kind == "navigator") payload = this._reflect(raw.Navigator);
        else if (_job.kind == "navigator_settings")
            payload = this._activeNavigatorSettingsPayload(raw.ActiveActor);
        else if (_job.kind == "constant") payload = this._constantPayload(_job.key);
        else if (_job.kind == "actor_core")
            payload = this._actorCorePayload(_job.target, raw.ActiveActor);
        else if (_job.kind == "actor_state") payload = this._reflect(_job.target.m);
        else if (_job.kind == "actor_properties")
        {
            payload = {
                current = this._reflect(_job.target.getCurrentProperties()),
                base_properties = this._reflect(_job.target.getBaseProperties())
            };
        }
        else if (_job.kind == "actor_skills_container")
            payload = this._reflect(_job.target.getSkills().m);
        else if (_job.kind == "actor_skill")
        {
            payload = {
                actor_id = _job.extra,
                skill = this._skillRecord(_job.target)
            };
        }
        else if (_job.kind == "actor_items_container")
            payload = this._reflect(_job.target.getItems().m);
        else if (_job.kind == "actor_item")
        {
            payload = {
                actor_id = _job.extra,
                item = this._itemRecord(_job.target)
            };
        }
        else if (_job.kind == "actor_ai")
        {
            local agent = null;
            try { agent = _job.target.getAIAgent(); } catch (_error) {}
            payload = agent == null ? null : this._reflect(agent.m);
        }
        else if (_job.kind == "tile") payload = this._tilePayload(_job.target);
        else if (_job.kind == "player_legal_meta"
            || _job.kind == "player_legal_tile"
            || _job.kind == "player_legal_actor")
        {
            payload = _job.target;
        }
        else if (_job.kind == "observation_memory")
        {
            payload = {
                original_key = _job.extra,
                fact = this._reflect(_job.target)
            };
        }
        else if (_job.kind == "manifest_expected") payload = _job.target;
        else if (_job.kind == "manifest_root") payload = this._manifestPayload();
        else throw "unknown combat sandbox job kind: " + _job.kind;

        this._emitRecord(raw, _job.section, _job.key, payload);

        if (_job.kind == "manifest_root")
        {
            local battle = this.State.battle_sequence;
            local generation = this.State.source_generation;
            local actorCount = this.State.actor_count;
            local tileCount = this.State.tile_count;
            local recordCount = this.State.expected_records.len();
            this.LastSnapshotKey = battle.tostring() + ":" + generation.tostring();
            this.State = null;
            ::logInfo(
                "[BB-Agent Combat Sandbox] complete battle=" + battle.tostring()
                + " generation=" + generation.tostring()
                + " actors=" + actorCount.tostring()
                + " tiles=" + tileCount.tostring()
                + " data_records=" + recordCount.tostring()
            );
        }
    },

    function begin(_raw)
    {
        if (!oracle.Enabled || _raw == null) return;
        local key = _raw.BattleSequence.tostring() + ":" + _raw.SourceGeneration.tostring();
        if (this.LastSnapshotKey == key) return;
        if (this.State != null
            && this.State.battle_sequence == _raw.BattleSequence
            && this.State.source_generation == _raw.SourceGeneration)
        {
            return;
        }
        if (this.State != null) this.cancel("superseded_generation");

        this.State = {
            raw = _raw,
            battle_sequence = _raw.BattleSequence,
            source_generation = _raw.SourceGeneration,
            jobs = [],
            cursor = 0,
            expected_records = [],
            expected_shards = [],
            actor_count = 0,
            tile_count = 0,
            finalizing = false,
            player_legal_projection = null
        };

        this._enqueue("player_legal_build", null, null, null, null, false);
        this._enqueue("raw_meta", "raw", "root");
        local fingerprintIndex = 0;
        foreach (value in _raw.RawSourceFingerprintInputs)
        {
            this._enqueue(
                "raw_fingerprint_input",
                "raw_fingerprint_input",
                fingerprintIndex.tostring(),
                value,
                fingerprintIndex
            );
            ++fingerprintIndex;
        }
        this._enqueue("tactical_state", "tactical_state", "root");
        this._enqueue("turn", "turn", "root");
        this._enqueue("entity_manager", "entity_manager", "root");
        this._enqueue("tactical_global", "tactical_global", "root");
        this._enqueue("navigator", "navigator", "root");
        this._enqueue("navigator_settings", "navigator_settings", "active_player");
        foreach (constantKey in [
            "movement", "direction", "tactical", "combat", "items",
            "skill_type", "item_slot", "body_part", "morale_state"
        ])
        {
            this._enqueue("constant", "constant", constantKey);
        }
        this._enqueueActors(_raw);
        this._enqueueTiles();

        ::logInfo(
            "[BB-Agent Combat Sandbox] staged battle=" + _raw.BattleSequence.tostring()
            + " generation=" + _raw.SourceGeneration.tostring()
            + " initial_jobs=" + this.State.jobs.len().tostring()
            + " actors=" + this.State.actor_count.tostring()
            + " tiles=" + this.State.tile_count.tostring()
        );
    },

    function pump()
    {
        if (!oracle.Enabled || this.State == null) return;
        local current = capture.getCurrentRawAcquisition();
        if (current == null)
        {
            this.cancel("generation_changed");
            return;
        }
        if (current.BattleSequence != this.State.battle_sequence
            || current.SourceGeneration != this.State.source_generation)
        {
            this.cancel("generation_changed");
            return;
        }

        local processed = 0;
        while (processed < this.RecordsPerPump && this.State != null)
        {
            if (this.State.cursor >= this.State.jobs.len())
            {
                if (!this.State.finalizing)
                {
                    this._enqueueManifestJobs();
                    continue;
                }
                break;
            }

            local job = this.State.jobs[this.State.cursor];
            ++this.State.cursor;
            try
            {
                this._processJob(job);
            }
            catch (error)
            {
                if (job.section == null || job.key == null)
                {
                    ::logError(
                        "[BB-Agent Combat Sandbox] job_error kind=" + job.kind
                        + " error=" + error.tostring()
                    );
                }
                else
                {
                    try { this._emitJobError(job, error); }
                    catch (transportError)
                    {
                        ::logError(
                            "[BB-Agent Combat Sandbox] transport_error kind=" + job.kind
                            + " error=" + transportError.tostring()
                        );
                        this.cancel("transport_error");
                        return;
                    }
                }
            }
            ++processed;

            if (this.State != null
                && this.State.cursor % 64 == 0)
            {
                ::logInfo(
                    "[BB-Agent Combat Sandbox] progress battle="
                    + this.State.battle_sequence.tostring()
                    + " generation=" + this.State.source_generation.tostring()
                    + " cursor=" + this.State.cursor.tostring()
                    + " jobs=" + this.State.jobs.len().tostring()
                );
            }
        }
    },

    function cancel(_reason)
    {
        if (this.State == null) return;
        ::logInfo(
            "[BB-Agent Combat Sandbox] cancelled battle="
            + this.State.battle_sequence.tostring()
            + " generation=" + this.State.source_generation.tostring()
            + " cursor=" + this.State.cursor.tostring()
            + " jobs=" + this.State.jobs.len().tostring()
            + " reason=" + _reason
        );
        this.State = null;
    }
};

::logInfo(
    "[BB-Agent Combat Sandbox] module_loaded schema="
    + ::BBAGENT_CombatSandbox.SchemaVersion
    + " staged=true records_per_update="
    + ::BBAGENT_CombatSandbox.RecordsPerPump.tostring()
    + " oracle_enabled=" + oracle.Enabled.tostring()
);