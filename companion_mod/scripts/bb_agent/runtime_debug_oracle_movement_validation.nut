local affordances = ::BBAGENT_Affordances;
local legal = ::BBAGENT_PlayerLegal;
local oracle = ::BBAGENT_DebugOracle;
local sandbox = ::BBAGENT_CombatSandbox;

oracle.MovementValidationSampleCap <- 6;

oracle._movementValidationAdd <- function(_samples, _seen, _role, _tileId, _node)
{
    if (_tileId == null || _tileId in _seen) return;
    if (_samples.len() >= this.MovementValidationSampleCap) return;
    _seen[_tileId] <- true;
    _samples.push({
        role = _role,
        tile_id = _tileId,
        model_reachable = _node != null,
        model_ap = _node == null ? null : _node.ap_spent,
        model_fatigue = _node == null ? null : _node.fatigue_spent,
        model_depth = _node == null ? null : _node.depth,
        model_previous_tile_id = _node == null ? null : _node.previous_tile_id
    });
};

oracle._movementValidationPlan <- function(_raw, _projection)
{
    local tree = affordances._movementReachability(_raw, _projection);
    local candidates = [];
    foreach (tileId, node in tree.nodes)
    {
        if (tileId == tree.origin_id) continue;
        candidates.push({ tile_id = tileId, node = node });
    }
    candidates.sort(@(a, b) a.tile_id <=> b.tile_id);

    local samples = [];
    local seen = {};
    local nearest = null;
    local farthest = null;
    local highestCost = null;
    foreach (candidate in candidates)
    {
        local node = candidate.node;
        if (nearest == null
            || node.depth < nearest.node.depth
            || (node.depth == nearest.node.depth
                && candidate.tile_id < nearest.tile_id))
        {
            nearest = candidate;
        }
        if (farthest == null
            || node.depth > farthest.node.depth
            || (node.depth == farthest.node.depth
                && candidate.tile_id < farthest.tile_id))
        {
            farthest = candidate;
        }
        if (highestCost == null
            || node.ap_spent > highestCost.node.ap_spent
            || (node.ap_spent == highestCost.node.ap_spent
                && node.fatigue_spent > highestCost.node.fatigue_spent)
            || (node.ap_spent == highestCost.node.ap_spent
                && node.fatigue_spent == highestCost.node.fatigue_spent
                && candidate.tile_id < highestCost.tile_id))
        {
            highestCost = candidate;
        }
    }

    if (nearest != null)
        this._movementValidationAdd(
            samples, seen, "nearest_reachable", nearest.tile_id, nearest.node
        );
    if (farthest != null)
        this._movementValidationAdd(
            samples, seen, "farthest_reachable", farthest.tile_id, farthest.node
        );
    if (highestCost != null)
        this._movementValidationAdd(
            samples, seen, "highest_cost_reachable", highestCost.tile_id, highestCost.node
        );

    local zocCounts = affordances._movementVisibleZocCounts(
        _projection,
        tree.tiles
    );
    foreach (candidate in candidates)
    {
        if (candidate.tile_id in zocCounts)
        {
            this._movementValidationAdd(
                samples, seen, "zoc_entry", candidate.tile_id, candidate.node
            );
            break;
        }
    }
    foreach (candidate in candidates)
    {
        local previous = candidate.node.previous_tile_id;
        if (previous != null && previous in zocCounts)
        {
            this._movementValidationAdd(
                samples, seen, "zoc_exit", candidate.tile_id, candidate.node
            );
            break;
        }
    }

    local visibleTiles = affordances._movementExactVisibleTileMap(_projection);
    local visibleIds = [];
    foreach (tileId, _tile in visibleTiles)
        if (tileId != tree.origin_id && !(tileId in tree.nodes)) visibleIds.push(tileId);
    visibleIds.sort();
    foreach (tileId in visibleIds)
    {
        local tile = visibleTiles[tileId];
        if (!tile.IsEmpty) continue;
        if (tile.Type == ::Const.Tactical.TerrainType.Impassable) continue;
        this._movementValidationAdd(
            samples, seen, "model_unreachable_visible", tileId, null
        );
        break;
    }

    return samples;
};

oracle._movementValidationCost <- function(_costs, _preferred, _fallback)
{
    if (_costs == null) return null;
    if (_preferred in _costs) return _costs[_preferred];
    if (_fallback in _costs) return _costs[_fallback];
    return null;
};

oracle._movementValidationSample <- function(_raw, _projection, _sample)
{
    local active = _raw.ActiveActor;
    local tiles = affordances._movementExactVisibleTileMap(_projection);
    if (!(_sample.tile_id in tiles))
    {
        _sample.error <- "destination_not_exact_visible";
        return _sample;
    }

    local navigator = _raw.Navigator;
    local settings = affordances._movementSettings(active, navigator);
    local origin = active.getTile();
    local destination = tiles[_sample.tile_id];
    local found = false;
    local costs = null;

    navigator.clearPath();
    navigator.clearVisualisation();
    try
    {
        found = navigator.findPath(origin, destination, settings, 0);
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
    _sample.native_ap <- this._movementValidationCost(
        costs,
        "ActionPointsRequired",
        "ActionPoints"
    );
    _sample.native_fatigue <- this._movementValidationCost(
        costs,
        "FatigueRequired",
        "Fatigue"
    );
    _sample.native_first_tile_id <- costs != null
        && "First" in costs
        && costs.First != null
        ? legal.tileID(costs.First)
        : null;
    _sample.native_end_tile_id <- costs != null
        && "End" in costs
        && costs.End != null
        ? legal.tileID(costs.End)
        : null;
    _sample.reachability_agreement <- _sample.model_reachable
        == _sample.native_complete;
    _sample.cost_agreement <- _sample.model_reachable
        && _sample.native_complete
        && _sample.native_ap == _sample.model_ap
        && _sample.native_fatigue == _sample.model_fatigue;
    return _sample;
};

local originalSandboxProcessJob = sandbox._processJob;
sandbox._processJob = function(_job)
{
    if (_job.kind == "movement_validation_sample")
    {
        if (!oracle.Enabled)
        {
            _job.target.error <- "debug_oracle_disabled";
            this._emitRecord(
                this.State.raw,
                _job.section,
                _job.key,
                _job.target
            );
            return;
        }
        local sample = oracle._movementValidationSample(
            this.State.raw,
            this.State.player_legal_projection,
            _job.target
        );
        this._emitRecord(this.State.raw, _job.section, _job.key, sample);
        return;
    }

    local wasPlayerLegalBuild = _job.kind == "player_legal_build";
    local ret = originalSandboxProcessJob.acall([this, _job]);
    if (!wasPlayerLegalBuild || this.State == null) return ret;
    if (!oracle.Enabled) return ret;
    if (this.State.player_legal_projection == null) return ret;

    local samples = [];
    try
    {
        samples = oracle._movementValidationPlan(
            this.State.raw,
            this.State.player_legal_projection
        );
    }
    catch (error)
    {
        this._enqueue(
            "movement_validation_sample",
            "debug_movement_validation",
            "plan_error",
            {
                role = "plan_error",
                tile_id = null,
                model_reachable = false,
                error = error.tostring()
            }
        );
        return ret;
    }

    foreach (index, sample in samples)
    {
        this._enqueue(
            "movement_validation_sample",
            "debug_movement_validation",
            index.tostring(),
            sample
        );
    }
    return ret;
};

::logInfo(
    "[BB-Agent DEBUG_ORACLE] movement_validation_loaded sample_cap=6 staged=true"
);
