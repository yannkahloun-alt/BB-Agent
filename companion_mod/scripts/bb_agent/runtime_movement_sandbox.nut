local wire = ::BBAGENT_Wire;
local capture = ::BBAGENT_Capture;
local legal = ::BBAGENT_PlayerLegal;
local affordances = ::BBAGENT_Affordances;
local oracle = ::BBAGENT_DebugOracle;

::BBAGENT_MovementSandbox <- {
    FramePrefix = "BBSANDBOX1",
    SchemaVersion = "bb-agent-movement-sandbox.v1",
    ChunkPayloadChars = 1200,
    MaxChunkLineBytes = 1400,
    MaxDecodedBytes = 4194304,
    MaxEncodedBytes = 6291456,
    LastSnapshotKey = null,
    LastAttemptKey = null,

    function _numberText(_value)
    {
        if (_value == null) return null;
        local kind = typeof _value;
        if (kind != "integer" && kind != "float")
            throw "movement sandbox numeric value has unsupported type";
        return _value.tostring();
    },

    function _numberArray(_values)
    {
        if (typeof _values != "array")
            throw "movement sandbox numeric table must be an array";
        local ret = [];
        foreach (value in _values) ret.push(this._numberText(value));
        return ret;
    },

    function _visibleActorFacts(_projection)
    {
        local ret = [];
        foreach (actor in _projection.state.combatants)
        {
            if (!actor.visible || actor.life_state != "ALIVE") continue;
            if (actor.position.representation != "EXACT") continue;
            ret.push({
                actor_id = actor.actor_id,
                relation = actor.relation,
                tile_id = actor.position.value,
                is_player_controlled = actor.is_player_controlled
            });
        }
        ret.sort(@(a, b) a.actor_id <=> b.actor_id);
        return ret;
    },

    function _visibleActorByTile(_projection)
    {
        local ret = {};
        foreach (actor in this._visibleActorFacts(_projection))
            ret[actor.tile_id] <- actor;
        return ret;
    },

    function _nativeProjectedTiles(_projection)
    {
        local ret = {};
        local size = ::Tactical.getMapSize();
        for (local x = 0; x < size.X; x = ++x)
        {
            for (local y = 0; y < size.Y; y = ++y)
            {
                if (!::Tactical.isValidTileSquare(x, y)) continue;
                local tile = ::Tactical.getTileSquare(x, y);
                local tileId = legal.tileID(tile);
                if (tileId in _projection.runtime.tile_records)
                    ret[tileId] <- tile;
            }
        }
        return ret;
    },

    function _tileFacts(_projection)
    {
        local ret = [];
        local nativeTiles = this._nativeProjectedTiles(_projection);
        local actorsByTile = this._visibleActorByTile(_projection);
        foreach (tileId, record in _projection.runtime.tile_records)
        {
            local tile = tileId in nativeTiles ? nativeTiles[tileId] : null;
            local visible = tileId in _projection.runtime.tile_visible;
            local discovered = tile != null ? tile.IsDiscovered : false;
            local occupancy = "UNKNOWN";
            if (visible)
            {
                if (tileId in actorsByTile)
                    occupancy = actorsByTile[tileId].relation;
                else if (tile != null && !tile.IsEmpty)
                    occupancy = "BLOCKED_OTHER";
                else
                    occupancy = "EMPTY";
            }

            local neighbors = [];
            foreach (neighborId in record.neighbor_ids) neighbors.push(neighborId);
            ret.push({
                tile_id = tileId,
                q = record.coordinate.q,
                r = record.coordinate.r,
                elevation = record.elevation,
                terrain = record.terrain,
                neighbor_ids = neighbors,
                visible = visible,
                discovered = discovered,
                visible_occupancy = occupancy,
                dynamic_effects = record.dynamic_effects
            });
        }
        ret.sort(@(a, b) a.tile_id <=> b.tile_id);
        return ret;
    },

    function _visibleZocFacts(_projection)
    {
        local visibleTiles = affordances._movementExactVisibleTileMap(_projection);
        local counts = affordances._movementVisibleZocCounts(_projection, visibleTiles);
        local ret = [];
        foreach (tileId, count in counts)
        {
            ret.push({
                tile_id = tileId,
                visible_hostile_zoc_count = count
            });
        }
        ret.sort(@(a, b) a.tile_id <=> b.tile_id);
        return ret;
    },

    function _movementContext(_raw, _projection)
    {
        local active = _raw.ActiveActor;
        local properties = active.getCurrentProperties();
        return {
            active_actor_id = _projection.runtime.active_actor_id,
            active_tile_id = legal.tileID(active.getTile()),
            action_points = this._numberText(active.getActionPoints()),
            action_points_max = this._numberText(active.getActionPointsMax()),
            fatigue = this._numberText(active.getFatigue()),
            fatigue_max = this._numberText(active.getFatigueMax()),
            movement_ap_costs = this._numberArray(active.getActionPointCosts()),
            movement_fatigue_costs = this._numberArray(active.getFatigueCosts()),
            level_action_point_cost = this._numberText(active.getLevelActionPointCost()),
            level_fatigue_cost = this._numberText(active.getLevelFatigueCost()),
            max_traversible_levels = this._numberText(active.getMaxTraversibleLevels()),
            fatigue_effect_mult = this._numberText(properties.FatigueEffectMult),
            is_rooted = properties.IsRooted,
            is_stunned = properties.IsStunned,
            is_immune_to_zone_of_control = properties.IsImmuneToZoneOfControl,
            movement_constants = {
                fatigue_cost_factor = this._numberText(::Const.Movement.FatigueCostFactor),
                zone_of_control_cost = "4",
                allow_zone_of_control_passing = true,
                level_climbing_fatigue_cost = this._numberText(
                    ::Const.Movement.LevelClimbingFatigueCost
                )
            },
            direction_values = {
                N = ::Const.Direction.N,
                NE = ::Const.Direction.NE,
                SE = ::Const.Direction.SE,
                S = ::Const.Direction.S,
                SW = ::Const.Direction.SW,
                NW = ::Const.Direction.NW
            },
            visible_hostile_zoc = this._visibleZocFacts(_projection)
        };
    },

    function _record(_raw, _projection)
    {
        local provenance = capture.State.Provenance;
        return {
            record_type = "MOVEMENT_SANDBOX",
            schema_version = this.SchemaVersion,
            battle_sequence = _raw.BattleSequence,
            source_generation = _raw.SourceGeneration,
            raw_source_fingerprint = wire.canonicalHash(_raw.RawSourceFingerprintInputs),
            runtime_game_version = provenance.GameVersion,
            ruleset_game_version = capture.SupportedGameVersion,
            ruleset_content_fingerprint = capture.RulesetContentFingerprint,
            companion_version = provenance.CompanionVersion,
            payload = {
                tiles = this._tileFacts(_projection),
                visible_actors = this._visibleActorFacts(_projection),
                movement_context = this._movementContext(_raw, _projection)
            }
        };
    },

    function _emitChunked(_record)
    {
        local raw = wire.canonicalJson(_record);
        if (raw.len() > this.MaxDecodedBytes)
            throw "movement sandbox record exceeds decoded payload bound";
        local digest = wire.sha256(raw);
        local encoded = wire.base64Url(raw);
        if (encoded.len() > this.MaxEncodedBytes)
            throw "movement sandbox record exceeds encoded payload bound";

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
                + _record.battle_sequence.tostring() + "|"
                + _record.source_generation.tostring() + "|"
                + index.tostring() + "|"
                + chunkCount.tostring() + "|"
                + raw.len().tostring() + "|"
                + digest + "|" + chunk;
            if (line.len() > this.MaxChunkLineBytes)
                throw "movement sandbox chunk exceeds log line bound";
            ::logInfo(line);
            ++index;
        }

        return {
            chunks = chunkCount,
            decoded_bytes = raw.len(),
            encoded_bytes = encoded.len()
        };
    },

    function capture(_raw, _projection)
    {
        local key = _raw.BattleSequence.tostring() + ":" + _raw.SourceGeneration.tostring();
        if (this.LastAttemptKey == key) return;
        this.LastAttemptKey = key;

        ::logInfo(
            "[BB-Agent Sandbox] capture_attempt battle=" + _raw.BattleSequence.tostring()
            + " generation=" + _raw.SourceGeneration.tostring()
            + " oracle_enabled=" + oracle.Enabled.tostring()
        );

        if (!oracle.Enabled)
        {
            ::logInfo("[BB-Agent Sandbox] skipped reason=oracle_disabled");
            return;
        }
        if (this.LastSnapshotKey == key) return;

        try
        {
            local record = this._record(_raw, _projection);
            local emitted = this._emitChunked(record);
            this.LastSnapshotKey = key;
            ::logInfo(
                "[BB-Agent Sandbox] emitted battle=" + _raw.BattleSequence.tostring()
                + " generation=" + _raw.SourceGeneration.tostring()
                + " chunks=" + emitted.chunks.tostring()
                + " decoded_bytes=" + emitted.decoded_bytes.tostring()
                + " encoded_bytes=" + emitted.encoded_bytes.tostring()
            );
        }
        catch (error)
        {
            // Diagnostic snapshot failure must never invalidate the live capture.
            ::logError("[BB-Agent Sandbox] error=" + error.tostring());
        }
    }
};

::logInfo(
    "[BB-Agent Sandbox] module_loaded schema="
    + ::BBAGENT_MovementSandbox.SchemaVersion
    + " oracle_enabled=" + oracle.Enabled.tostring()
);
