local wire = ::BBAGENT_Wire;
local capture = ::BBAGENT_Capture;
local legal = ::BBAGENT_PlayerLegal;
local affordances = ::BBAGENT_Affordances;
local oracle = ::BBAGENT_DebugOracle;

::BBAGENT_MovementSandbox <- {
    FramePrefix = "BBSANDBOX1",
    SchemaVersion = "bb-agent-movement-sandbox.v1",
    MaxDecodedBytes = 4194304,
    MaxEncodedBytes = 6291456,
    LastSnapshotKey = null,

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
                player_legal_state = _projection.state,
                movement_context = this._movementContext(_raw, _projection)
            }
        };
    },

    function _encode(_record)
    {
        local raw = wire.canonicalJson(_record);
        if (raw.len() > this.MaxDecodedBytes)
            throw "movement sandbox record exceeds decoded payload bound";
        local frame = this.FramePrefix + "|" + raw.len() + "|" + wire.sha256(raw)
            + "|" + wire.base64Url(raw);
        if (frame.len() > this.MaxEncodedBytes)
            throw "movement sandbox record exceeds encoded payload bound";
        return frame;
    },

    function capture(_raw, _projection)
    {
        if (!oracle.Enabled) return;
        local key = _raw.BattleSequence.tostring() + ":" + _raw.SourceGeneration.tostring();
        if (this.LastSnapshotKey == key) return;

        try
        {
            local record = this._record(_raw, _projection);
            local frame = this._encode(record);
            ::logInfo(frame);
            this.LastSnapshotKey = key;
            ::logInfo(
                "[BB-Agent Sandbox] emitted battle=" + _raw.BattleSequence
                + " generation=" + _raw.SourceGeneration
                + " bytes=" + frame.len()
            );
        }
        catch (error)
        {
            // Diagnostic snapshot failure must never invalidate the live capture.
            ::logError("[BB-Agent Sandbox] error=" + error);
        }
    }
};
