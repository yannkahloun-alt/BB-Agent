local affordances = ::BBAGENT_Affordances;
local legal = ::BBAGENT_PlayerLegal;
local oracle = ::BBAGENT_DebugOracle;
local sandbox = ::BBAGENT_CombatSandbox;

oracle.RememberedMovementValidationSampleCap <- 2;

oracle._movementValidationHexDistance <- function(_left, _right)
{
    local dq = _left.q - _right.q;
    local dr = _left.r - _right.r;
    return (::Math.abs(dq) + ::Math.abs(dr) + ::Math.abs(dq + dr)) / 2;
};

oracle._rememberedMovementValidationPlan <- function(_raw, _projection, _nativeTiles)
{
    local activeId = legal.tileID(_raw.ActiveActor.getTile());
    if (!(activeId in _projection.runtime.tile_records)) return [];
    local origin = _projection.runtime.tile_records[activeId].coordinate;
    local candidates = [];

    foreach (tile in _projection.state.tiles)
    {
        if (tile.visibility != "REMEMBERED") continue;
        if (!(tile.tile_id in _nativeTiles)) continue;
        if (!(tile.tile_id in _projection.runtime.tile_records)) continue;
        local record = _projection.runtime.tile_records[tile.tile_id];
        candidates.push({
            tile_id = tile.tile_id,
            distance = this._movementValidationHexDistance(origin, record.coordinate)
        });
    }
    if (candidates.len() == 0) return [];

    candidates.sort(@(a, b) a.tile_id <=> b.tile_id);
    local nearest = candidates[0];
    local farthest = candidates[0];
    foreach (candidate in candidates)
    {
        if (candidate.distance < nearest.distance
            || (candidate.distance == nearest.distance
                && candidate.tile_id < nearest.tile_id))
        {
            nearest = candidate;
        }
        if (candidate.distance > farthest.distance
            || (candidate.distance == farthest.distance
                && candidate.tile_id < farthest.tile_id))
        {
            farthest = candidate;
        }
    }

    local ret = [];
    ret.push({
        role = "remembered_nearest",
        tile_id = nearest.tile_id,
        player_legal_visibility = "REMEMBERED",
        model_scope_enumerated = false,
        distance = nearest.distance
    });
    if (farthest.tile_id != nearest.tile_id
        && ret.len() < this.RememberedMovementValidationSampleCap)
    {
        ret.push({
            role = "remembered_farthest",
            tile_id = farthest.tile_id,
            player_legal_visibility = "REMEMBERED",
            model_scope_enumerated = false,
            distance = farthest.distance
        });
    }
    return ret;
};

oracle._rememberedMovementValidationSample <- function(_raw, _nativeTiles, _sample)
{
    if (!(_sample.tile_id in _nativeTiles))
    {
        _sample.error <- "remembered_native_tile_missing";
        return _sample;
    }

    local active = _raw.ActiveActor;
    local destination = _nativeTiles[_sample.tile_id];
    local navigator = _raw.Navigator;
    local settings = affordances._movementSettings(active, navigator);
    local found = false;
    local costs = null;

    navigator.clearPath();
    navigator.clearVisualisation();
    try
    {
        found = navigator.findPath(active.getTile(), destination, settings, 0);
        if (found)
        {
            costs = navigator.getCostForPath(
                active,
                settings,
                active.getActionPoints(),
                active.getFatigueMax() - active.getFatigue()
            );
        }
    }
    catch (error)
    {
        _sample.error <- error.tostring();
    }
    navigator.clearPath();
    navigator.clearVisualisation();

    _sample.native_found <- found;
    _sample.native_complete <- costs != null
        && "IsComplete" in costs
        && costs.IsComplete;
    _sample.native_tiles <- costs != null && "Tiles" in costs ? costs.Tiles : null;
    _sample.native_ap <- oracle._movementValidationCost(
        costs,
        "ActionPointsRequired",
        "ActionPoints"
    );
    _sample.native_fatigue <- oracle._movementValidationCost(
        costs,
        "FatigueRequired",
        "Fatigue"
    );
    return _sample;
};

local originalProcessDiscovery = sandbox._processDiscovery;
sandbox._processDiscovery = function(_job)
{
    local isTile = _job.kind == "discover_tile";
    local x = isTile ? _job.extra.x : null;
    local y = isTile ? _job.extra.y : null;
    local ret = originalProcessDiscovery.acall([this, _job]);
    if (!isTile || this.State == null) return ret;

    local size = this.State.map_size;
    if (size != null && x >= size.X)
    {
        this.State.tile_discovery_complete = true;
        return ret;
    }
    if (size == null || !::Tactical.isValidTileSquare(x, y)) return ret;
    local tile = ::Tactical.getTileSquare(x, y);
    this.State.native_tile_by_id[this._tileID(tile)] <- tile;
    return ret;
};

local originalSandboxProcessJob = sandbox._processJob;
sandbox._processJob = function(_job)
{
    if (_job.kind == "remembered_movement_validation_plan")
    {
        if (!oracle.Enabled || this.State == null) return;
        if (!this.State.tile_discovery_complete)
        {
            this._enqueue(
                "remembered_movement_validation_plan",
                null,
                null,
                null,
                null,
                false
            );
            return;
        }

        local samples = oracle._rememberedMovementValidationPlan(
            this.State.raw,
            this.State.player_legal_projection,
            this.State.native_tile_by_id
        );
        foreach (index, sample in samples)
        {
            this._enqueue(
                "remembered_movement_validation_sample",
                "debug_movement_validation",
                "remembered_" + index.tostring(),
                sample
            );
        }
        return;
    }

    if (_job.kind == "remembered_movement_validation_sample")
    {
        if (!oracle.Enabled || this.State == null) return;
        local sample = oracle._rememberedMovementValidationSample(
            this.State.raw,
            this.State.native_tile_by_id,
            _job.target
        );
        this._emitRecord(this.State.raw, _job.section, _job.key, sample);
        return;
    }

    local wasPlayerLegalBuild = _job.kind == "player_legal_build";
    local ret = originalSandboxProcessJob.acall([this, _job]);
    if (!oracle.Enabled || !wasPlayerLegalBuild || this.State == null) return ret;
    if (this.State.player_legal_projection == null) return ret;
    this._enqueue(
        "remembered_movement_validation_plan",
        null,
        null,
        null,
        null,
        false
    );
    return ret;
};

local originalBegin = sandbox.begin;
sandbox.begin = function(_raw)
{
    originalBegin.acall([this, _raw]);
    if (this.State == null) return;
    this.State.native_tile_by_id <- {};
    this.State.tile_discovery_complete <- false;
};

::logInfo(
    "[BB-Agent DEBUG_ORACLE] remembered_movement_validation_loaded sample_cap=2"
    + " discovery_index=reused staged=true"
);
