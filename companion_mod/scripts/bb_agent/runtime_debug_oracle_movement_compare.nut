local affordances = ::BBAGENT_Affordances;
local oracle = ::BBAGENT_DebugOracle;
local legal = ::BBAGENT_PlayerLegal;

oracle.MaxMovementCompareSamples <- 3;

oracle._movementCompareCost <- function(_costs, _preferred, _fallback)
{
    if (_costs == null) return null;
    if (_preferred in _costs) return _costs[_preferred];
    if (_fallback in _costs) return _costs[_fallback];
    return null;
};

oracle._movementComparePath <- function(_active, _costs)
{
    local originId = legal.tileID(_active.getTile());
    local ret = [];
    local seen = {};
    seen[originId] <- true;
    foreach (name in ["First", "SecondLastBeforeEnd", "LastBeforeEnd", "End"])
    {
        if (_costs == null || !(name in _costs) || _costs[name] == null) continue;
        local tileId = legal.tileID(_costs[name]);
        if (tileId in seen) continue;
        seen[tileId] <- true;
        ret.push(tileId);
    }
    return ret;
};

oracle._movementComparePathText <- function(_ids)
{
    local ret = "[";
    for (local i = 0; i < _ids.len(); i = ++i)
    {
        if (i != 0) ret += ",";
        ret += _ids[i];
    }
    return ret + "]";
};

oracle._movementCompareActionPath <- function(_action)
{
    local ret = [];
    foreach (tileId in _action.resolved_path) ret.push(tileId);
    return ret;
};

oracle._movementComparePathsEqual <- function(_a, _b)
{
    if (_a.len() != _b.len()) return false;
    for (local i = 0; i < _a.len(); i = ++i)
        if (_a[i] != _b[i]) return false;
    return true;
};

oracle._movementCompareContainsAction <- function(_actions, _candidate)
{
    foreach (action in _actions)
        if (action.destination_tile_id == _candidate.destination_tile_id) return true;
    return false;
};

oracle._movementCompareDivergence <- function(
    _active,
    _tiles,
    _destination,
    _localPath,
    _nativePath,
    _sampleIndex
)
{
    local limit = ::Math.min(_localPath.len(), _nativePath.len());
    local divergence = -1;
    for (local i = 0; i < limit; i = ++i)
    {
        if (_localPath[i] != _nativePath[i])
        {
            divergence = i;
            break;
        }
    }
    if (divergence < 0) return;

    local fromTile = divergence == 0
        ? _active.getTile()
        : _tiles[_localPath[divergence - 1]];
    local localNext = _tiles[_localPath[divergence]];
    local nativeNext = _tiles[_nativePath[divergence]];

    local localDirection = "unavailable";
    local nativeDirection = "unavailable";
    local localRemaining = "unavailable";
    local nativeRemaining = "unavailable";
    try
    {
        localDirection = fromTile.getDirectionTo(localNext).tostring();
        nativeDirection = fromTile.getDirectionTo(nativeNext).tostring();
        localRemaining = localNext.getDistanceTo(_destination).tostring();
        nativeRemaining = nativeNext.getDistanceTo(_destination).tostring();
    }
    catch (_error)
    {
    }

    this._log(
        "movement_compare_divergence sample=" + _sampleIndex
        + " index=" + divergence
        + " from=" + legal.tileID(fromTile)
        + " local_next=" + _localPath[divergence]
        + " local_dir=" + localDirection
        + " local_remaining=" + localRemaining
        + " native_next=" + _nativePath[divergence]
        + " native_dir=" + nativeDirection
        + " native_remaining=" + nativeRemaining
    );
};

// Pick at most three high-information samples: shortest path, longest anchorable
// path (<=4 steps), and one path with an AoO contingency when available.
oracle._movementCompareSamples <- function(_actions)
{
    local moves = [];
    foreach (action in _actions)
        if (action.kind == "MOVE_TO") moves.push(action);
    if (moves.len() == 0) return [];

    local shortest = moves[0];
    local longest = null;
    local zoc = null;
    foreach (action in moves)
    {
        local length = action.resolved_path.len();
        if (length < shortest.resolved_path.len()
            || (length == shortest.resolved_path.len()
                && action.destination_tile_id < shortest.destination_tile_id))
        {
            shortest = action;
        }
        if (length <= 4
            && (longest == null
                || length > longest.resolved_path.len()
                || (length == longest.resolved_path.len()
                    && action.destination_tile_id < longest.destination_tile_id)))
        {
            longest = action;
        }
        if (action.contingent_reactions.len() != 0
            && length <= 4
            && (zoc == null || action.destination_tile_id < zoc.destination_tile_id))
        {
            zoc = action;
        }
    }

    local ret = [shortest];
    if (longest != null && !this._movementCompareContainsAction(ret, longest))
        ret.push(longest);
    if (zoc != null && !this._movementCompareContainsAction(ret, zoc)
        && ret.len() < this.MaxMovementCompareSamples)
    {
        ret.push(zoc);
    }
    if (ret.len() < this.MaxMovementCompareSamples)
    {
        foreach (action in moves)
        {
            if (action.resolved_path.len() > 4) continue;
            if (this._movementCompareContainsAction(ret, action)) continue;
            ret.push(action);
            if (ret.len() >= this.MaxMovementCompareSamples) break;
        }
    }
    return ret;
};

oracle._compareOneMovement <- function(_raw, _projection, _action, _sampleIndex)
{
    local active = _raw.ActiveActor;
    local navigator = _raw.Navigator;
    local tiles = affordances._movementExactVisibleTileMap(_projection);
    if (!(_action.destination_tile_id in tiles))
        throw "DEBUG_ORACLE movement sample destination is not exact-visible";
    local destination = tiles[_action.destination_tile_id];
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
            settings.ZoneOfControlCost = 0;
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
        navigator.clearPath();
        navigator.clearVisualisation();
        throw error;
    }
    navigator.clearPath();
    navigator.clearVisualisation();

    local localPath = this._movementCompareActionPath(_action);
    local nativePath = this._movementComparePath(active, costs);
    local nativeTiles = costs != null && "Tiles" in costs ? costs.Tiles : null;
    local nativeAP = this._movementCompareCost(
        costs,
        "ActionPointsRequired",
        "ActionPoints"
    );
    local nativeFatigue = this._movementCompareCost(
        costs,
        "FatigueRequired",
        "Fatigue"
    );
    local complete = costs != null && "IsComplete" in costs && costs.IsComplete;
    local anchorCoverage = nativeTiles != null
        && localPath.len() <= 4
        && nativePath.len() == nativeTiles;
    local pathMatch = anchorCoverage
        && this._movementComparePathsEqual(localPath, nativePath);
    local costMatch = nativeAP == _action.ap_cost.value
        && nativeFatigue == _action.fatigue_cost.value;
    local match = found && complete && nativeTiles != 0 && pathMatch && costMatch;

    this._log(
        "movement_compare sample=" + _sampleIndex
        + " destination=" + _action.destination_tile_id
        + " found=" + found.tostring()
        + " complete=" + complete.tostring()
        + " tiles=" + (nativeTiles == null ? "null" : nativeTiles.tostring())
        + " local_path=" + this._movementComparePathText(localPath)
        + " native_path=" + this._movementComparePathText(nativePath)
        + " local_ap=" + _action.ap_cost.value
        + " native_ap=" + (nativeAP == null ? "null" : nativeAP.tostring())
        + " local_fat=" + _action.fatigue_cost.value
        + " native_fat=" + (nativeFatigue == null ? "null" : nativeFatigue.tostring())
        + " anchor_coverage=" + anchorCoverage.tostring()
        + " path_match=" + pathMatch.tostring()
        + " cost_match=" + costMatch.tostring()
        + " match=" + match.tostring()
    );

    if (!pathMatch && anchorCoverage)
    {
        this._movementCompareDivergence(
            active,
            tiles,
            destination,
            localPath,
            nativePath,
            _sampleIndex
        );
    }
    return match;
};

oracle.compareMovementActions <- function(_raw, _projection, _actions)
{
    if (!this.Enabled) return;
    local samples = this._movementCompareSamples(_actions);
    this._log(
        "movement_compare_begin samples=" + samples.len()
        + " max_samples=" + this.MaxMovementCompareSamples
    );

    local mismatches = 0;
    for (local i = 0; i < samples.len(); i = ++i)
    {
        if (!this._compareOneMovement(_raw, _projection, samples[i], i + 1))
            ++mismatches;
    }

    this._log(
        "movement_compare_end samples=" + samples.len()
        + " mismatches=" + mismatches
    );
    if (mismatches != 0)
        throw "DEBUG_ORACLE movement comparison mismatch";
};

local originalMoveActions = affordances._moveActions;
affordances._moveActions = function(_raw, _projection)
{
    local actions = originalMoveActions.acall([this, _raw, _projection]);
    if (oracle.Enabled)
        oracle.compareMovementActions(_raw, _projection, actions);
    return actions;
};
