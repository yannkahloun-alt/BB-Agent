local wire = ::BBAGENT_Wire;
local capture = ::BBAGENT_Capture;
local liveExport = ::BBAGENT_LiveExport;
local legal = ::BBAGENT_PlayerLegal;
local affordances = ::BBAGENT_Affordances;

::BBAGENT_DebugOracle <- {
    Version = ::BBAGENT_DebugOracleDef.Version,
    PendingSnapshot = null,
    LastAdjacencyMismatch = null,
    MaxDecodedRecordBytes = 2097152,
    MaxEncodedFrameBytes = 3145728,
    DiagnosticMaxErrorChars = 240,

    function _sanitize(_value)
    {
        local text = _value == null ? "null" : _value.tostring();
        text = split(text, "\r\n\t").join(" ");
        if (text.len() > this.DiagnosticMaxErrorChars)
            text = text.slice(0, this.DiagnosticMaxErrorChars);
        return text;
    },

    function _tileID(_tile)
    {
        return legal.tileID(_tile);
    },

    function _nativeNeighborIDs(_tile)
    {
        local ret = array(6, null);
        local directions = legal._nativeDirections();
        for (local i = 0; i < 6; i = ++i)
        {
            local direction = directions[i];
            if (!_tile.hasNextTile(direction)) continue;
            local next = _tile.getNextTile(direction);
            if (next != null) ret[i] = this._tileID(next);
        }
        return ret;
    },

    function _findTile(_tileId)
    {
        local size = ::Tactical.getMapSize();
        for (local x = 0; x < size.X; x = ++x)
        {
            for (local y = 0; y < size.Y; y = ++y)
            {
                if (!::Tactical.isValidTileSquare(x, y)) continue;
                local tile = ::Tactical.getTileSquare(x, y);
                if (this._tileID(tile) == _tileId) return tile;
            }
        }
        return null;
    },

    function _rawTile(_tile)
    {
        if (_tile == null) return null;
        return {
            tile_id = this._tileID(_tile),
            square_x = _tile.SquareCoords.X,
            square_y = _tile.SquareCoords.Y,
            level = _tile.Level,
            type = _tile.Type,
            subtype = _tile.Subtype,
            visible_for_player = _tile.IsVisibleForPlayer,
            discovered = _tile.IsDiscovered,
            empty = _tile.IsEmpty,
            native_neighbor_ids = this._nativeNeighborIDs(_tile)
        };
    },

    function _rawTiles()
    {
        local ret = [];
        local size = ::Tactical.getMapSize();
        for (local x = 0; x < size.X; x = ++x)
        {
            for (local y = 0; y < size.Y; y = ++y)
            {
                if (!::Tactical.isValidTileSquare(x, y)) continue;
                ret.push(this._rawTile(::Tactical.getTileSquare(x, y)));
            }
        }
        ret.sort(@(a, b) a.tile_id <=> b.tile_id);
        return ret;
    },

    function _rawActors(_raw)
    {
        local ret = [];
        local groups = _raw.EntityManager.getAllInstances();
        foreach (group in groups)
        {
            foreach (actor in group)
            {
                if (actor == null || !("isPlayerControlled" in actor)) continue;
                local placed = actor.isPlacedOnMap();
                ret.push({
                    runtime_actor_id = actor.getID().tostring(),
                    canonical_actor_id = legal.actorID(actor),
                    player_controlled = actor.isPlayerControlled(),
                    alive = actor.isAlive(),
                    placed = placed,
                    hidden_to_player = placed && !actor.isPlayerControlled()
                        ? actor.isHiddenToPlayer()
                        : false,
                    faction = actor.getFaction(),
                    tile_id = placed ? this._tileID(actor.getTile()) : null,
                    hit_points = actor.getHitpoints(),
                    action_points = actor.getActionPoints(),
                    fatigue = actor.getFatigue(),
                    fatigue_max = actor.getFatigueMax(),
                    morale = actor.getMoraleState()
                });
            }
        }
        ret.sort(@(a, b) a.runtime_actor_id <=> b.runtime_actor_id);
        return ret;
    },

    function _stateNeighbors(_projection, _tileId)
    {
        foreach (tile in _projection.state.tiles)
            if (tile.tile_id == _tileId) return tile.neighbors;
        return null;
    },

    function recordAdjacencyMismatch(_projection, _fromId, _toId)
    {
        local fromTile = this._findTile(_fromId);
        local toTile = this._findTile(_toId);
        local fromInProjection = _fromId in _projection.runtime.tile_records;
        local toInProjection = _toId in _projection.runtime.tile_records;
        local runtimeNeighbors = fromInProjection
            ? _projection.runtime.tile_records[_fromId].neighbor_ids
            : null;

        this.LastAdjacencyMismatch = {
            from_tile_id = _fromId,
            to_tile_id = _toId,
            from_in_projection = fromInProjection,
            to_in_projection = toInProjection,
            from_visible_in_projection = _fromId in _projection.runtime.tile_visible,
            to_visible_in_projection = _toId in _projection.runtime.tile_visible,
            raw_from = this._rawTile(fromTile),
            raw_to = this._rawTile(toTile),
            projected_runtime_neighbor_ids = runtimeNeighbors,
            projected_state_neighbors = fromInProjection
                ? this._stateNeighbors(_projection, _fromId)
                : null
        };
    },

    function snapshot(_raw)
    {
        return {
            oracle_version = this.Version,
            battle_sequence = _raw.BattleSequence,
            source_generation = _raw.SourceGeneration,
            raw_source_fingerprint = wire.canonicalHash(_raw.RawSourceFingerprintInputs),
            active_runtime_actor_id = _raw.ActiveActor.getID().tostring(),
            active_tile_id = this._tileID(_raw.ActiveActor.getTile()),
            raw_actors = this._rawActors(_raw),
            raw_tiles = this._rawTiles(),
            adjacency_mismatch = null,
            production_last_error = null,
            production_ready_after_handle = null
        };
    },

    function emit(_snapshot)
    {
        local record = liveExport._common("DECISION_READY");
        record.battle_sequence <- _snapshot.battle_sequence;
        record.source_generation <- _snapshot.source_generation;
        record.raw_source_fingerprint <- _snapshot.raw_source_fingerprint;
        record.information_profile <- "omniscient_debug";
        record.payload <- _snapshot;

        local raw = wire.canonicalJson(record);
        if (raw.len() > this.MaxDecodedRecordBytes)
            throw "debug oracle record exceeds decoded payload bound";
        local frame = wire.encodeFrame(record);
        if (frame.len() > this.MaxEncodedFrameBytes)
            throw "debug oracle record exceeds encoded frame bound";
        ::logInfo(frame);
        ::logInfo(
            "[BB-Agent Oracle] READY battle=" + _snapshot.battle_sequence
            + " generation=" + _snapshot.source_generation
            + " profile=omniscient_debug"
        );
    }
};

local oracle = ::BBAGENT_DebugOracle;

// Observe failures in the production topology check without changing its result.
if ("_canonicalNeighbors" in affordances)
{
    local originalCanonicalNeighbors = affordances._canonicalNeighbors;
    affordances._canonicalNeighbors = function(_projection, _fromId, _toId)
    {
        local result = originalCanonicalNeighbors.acall(
            [this, _projection, _fromId, _toId]
        );
        if (!result)
            oracle.recordAdjacencyMismatch(_projection, _fromId, _toId);
        return result;
    };
}

// Snapshot raw/omniscient truth before production projection/acquisition starts.
// The snapshot contains JSON values only, never live runtime objects.
local originalReadyState = liveExport._readyState;
liveExport._readyState = function(_raw)
{
    oracle.PendingSnapshot = null;
    oracle.LastAdjacencyMismatch = null;
    try
    {
        oracle.PendingSnapshot = oracle.snapshot(_raw);
    }
    catch (error)
    {
        ::logError(
            "[BB-Agent Oracle] snapshot_error error=" + oracle._sanitize(error)
        );
    }
    return originalReadyState.acall([this, _raw]);
};

// Emit the oracle twin after the production handler has finished. Debug failure
// is isolated and never changes capture readiness or production invalidation.
local originalHandleLifecycleEvent = liveExport.handleLifecycleEvent;
liveExport.handleLifecycleEvent = function(_event)
{
    local result = originalHandleLifecycleEvent.acall([this, _event]);
    if (_event != null
        && _event.RecordType == "DECISION_READY"
        && oracle.PendingSnapshot != null)
    {
        local snapshot = oracle.PendingSnapshot;
        snapshot.adjacency_mismatch = oracle.LastAdjacencyMismatch;
        snapshot.production_last_error = capture.State.LastError;
        snapshot.production_ready_after_handle = capture.State.IsReady;
        try
        {
            oracle.emit(snapshot);
        }
        catch (error)
        {
            ::logError(
                "[BB-Agent Oracle] emit_error error=" + oracle._sanitize(error)
            );
        }
        oracle.PendingSnapshot = null;
        oracle.LastAdjacencyMismatch = null;
    }
    return result;
};
