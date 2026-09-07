local affordances = ::BBAGENT_Affordances;
local legal = ::BBAGENT_PlayerLegal;
local oracle = ::BBAGENT_DebugOracle;

// Pinned Battle Brothers scripts 162f498ac7c49b4c317bbf54718a595ecef6a65a
// expose tactical paths through getCostForPath() summaries rather than a script
// getPath accessor. Real 1.5.2.3 traces show First/SecondLastBeforeEnd/
// LastBeforeEnd/End are native path anchors. Sweep the stored native path across
// AP budgets, merge those ordered anchors, and validate every appended step against
// the canonical player-legal topology. Tiles remains only a zero/nonzero sentinel.
affordances._canonicalNeighbors <- function(_projection, _fromId, _toId)
{
    if (!(_fromId in _projection.runtime.tile_records)) return false;
    if (!(_toId in _projection.runtime.tile_records)) return false;
    local record = _projection.runtime.tile_records[_fromId];
    foreach (neighborId in record.neighbor_ids)
        if (neighborId == _toId) return true;
    return false;
};

affordances._oracleCostAnchorID <- function(_costs, _name)
{
    if (_costs == null || !(_name in _costs) || _costs[_name] == null)
        return "null";
    try
    {
        return legal.tileID(_costs[_name]);
    }
    catch (_error)
    {
        return "unreadable";
    }
};

affordances._traceOracleCostAnchors <- function(_label, _costs)
{
    if (!oracle.Enabled || _costs == null) return;
    local tiles = "missing";
    if ("Tiles" in _costs) tiles = _costs.Tiles.tostring();
    oracle._log(
        "native_cost_anchors label=" + _label
        + " tiles=" + tiles
        + " first=" + this._oracleCostAnchorID(_costs, "First")
        + " second_last=" + this._oracleCostAnchorID(_costs, "SecondLastBeforeEnd")
        + " last=" + this._oracleCostAnchorID(_costs, "LastBeforeEnd")
        + " end=" + this._oracleCostAnchorID(_costs, "End")
    );
};

affordances._nativeCostAnchors <- function(_costs)
{
    local ret = [];
    foreach (name in ["First", "SecondLastBeforeEnd", "LastBeforeEnd", "End"])
    {
        if (!(name in _costs) || _costs[name] == null) continue;
        local tile = _costs[name];
        local tileId = legal.tileID(tile);
        local duplicate = false;
        foreach (existing in ret)
        {
            if (legal.tileID(existing) == tileId)
            {
                duplicate = true;
                break;
            }
        }
        if (!duplicate) ret.push(tile);
    }
    return ret;
};

affordances._nativeCostPrefixPath <- function(
    _navigator,
    _active,
    _settings,
    _costs,
    _destination,
    _projection
)
{
    if (!("Tiles" in _costs) || typeof _costs.Tiles != "integer" || _costs.Tiles <= 0)
        throw "native movement preview returned no affordable movement prefix";
    if (!("IsComplete" in _costs) || typeof _costs.IsComplete != "bool" || !_costs.IsComplete)
        throw "native movement path reconstruction requires a complete path";
    if (!("End" in _costs) || _costs.End == null)
        throw "native movement preview returned no complete path endpoint";
    if (legal.tileID(_costs.End) != legal.tileID(_destination))
        throw "native complete movement endpoint differs from requested destination";

    local apRequired = this._movementCost(
        _costs,
        "ActionPointsRequired",
        "ActionPoints"
    );
    if (apRequired <= 0)
        throw "native movement path has steps but no positive action-point cost";

    local fatigueAvailable = _active.getFatigueMax() - _active.getFatigue();
    local path = [];
    local originTile = _active.getTile();
    local originId = legal.tileID(originTile);
    local lastTile = originTile;
    local lastTileId = originId;
    local destinationId = legal.tileID(_destination);
    local seen = {};
    seen[originId] <- true;

    for (local apBudget = 0; apBudget <= apRequired; apBudget = ++apBudget)
    {
        local prefix = _navigator.getCostForPath(
            _active,
            _settings,
            apBudget,
            fatigueAvailable
        );
        if (!("Tiles" in prefix) || typeof prefix.Tiles != "integer" || prefix.Tiles < 0)
            throw "native movement prefix returned an invalid movement sentinel";
        if (prefix.Tiles == 0) continue;
        if (!("End" in prefix) || prefix.End == null)
            throw "native movement prefix advanced without an endpoint";

        local anchors = this._nativeCostAnchors(prefix);
        if (anchors.len() == 0)
            throw "native movement prefix exposed no path anchors";

        foreach (tile in anchors)
        {
            local tileId = legal.tileID(tile);
            if (tileId == originId || tileId in seen) continue;
            if (!(tileId in _projection.runtime.tile_records))
                throw "native movement path leaves the player-legal canonical map";
            if (!this._canonicalNeighbors(_projection, lastTileId, tileId))
            {
                this._traceOracleCostAnchors("full", _costs);
                this._traceOracleCostAnchors("prefix_" + apBudget, prefix);
                oracle.reportMovementTopologyMismatch(
                    _navigator,
                    _active,
                    _settings,
                    _costs,
                    _destination,
                    _projection,
                    lastTile,
                    tile
                );
                throw "native movement cost anchors left a canonical path gap";
            }

            path.push(tile);
            seen[tileId] <- true;
            lastTile = tile;
            lastTileId = tileId;
        }

        if (lastTileId == destinationId) break;
    }

    if (path.len() == 0)
        throw "native movement prefixes produced no ordered path steps";
    if (lastTileId != destinationId)
        throw "reconstructed native movement path does not terminate at destination";
    return path;
};

// Replace movement enumeration only. Skill, wait/end-turn, equipment, identity,
// and the hardening acquire wrapper remain unchanged.
affordances._moveActions = function(_raw, _projection)
{
    local ret = [];
    local active = _raw.ActiveActor;
    local actorId = _projection.runtime.active_actor_id;
    local navigator = _raw.Navigator;
    local targetTiles = this._visibleTargetTiles(_projection);
    foreach (destination in targetTiles)
    {
        if (destination.ID == active.getTile().ID) continue;
        navigator.clearPath();
        navigator.clearVisualisation();
        local settings = this._movementSettings(active, navigator);
        local found = false;
        local complete = false;
        local costs = null;
        local pathTiles = null;
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
                if (!("Tiles" in costs) || typeof costs.Tiles != "integer" || costs.Tiles < 0)
                    throw "native movement preview returned an invalid movement sentinel";
                if (!("IsComplete" in costs) || typeof costs.IsComplete != "bool")
                    throw "native movement preview did not expose path completeness";
                if (costs.Tiles != 0 && costs.IsComplete)
                {
                    pathTiles = this._nativeCostPrefixPath(
                        navigator,
                        active,
                        settings,
                        costs,
                        destination,
                        _projection
                    );
                    complete = true;
                }
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
        if (!found || costs == null || costs.Tiles == 0 || !complete) continue;

        local apCost = this._movementCost(costs, "ActionPointsRequired", "ActionPoints");
        local fatigueCost = this._movementCost(costs, "FatigueRequired", "Fatigue");

        local action = this._baseAction(actorId, "MOVE_TO");
        action.destination_tile_id = legal.tileID(destination);
        foreach (tile in pathTiles) action.resolved_path.push(legal.tileID(tile));
        action.contingent_reactions = this._aooReactions(
            _projection.state,
            active,
            pathTiles
        );
        this._resolvedCosts(action, apCost, fatigueCost);
        ret.push(action);
    }
    return ret;
};
