local affordances = ::BBAGENT_Affordances;
local legal = ::BBAGENT_PlayerLegal;

// Pinned Battle Brothers scripts 162f498ac7c49b4c317bbf54718a595ecef6a65a
// expose tactical paths through getCostForPath() summaries (Tiles/End/IsComplete),
// not through a script getPath accessor. Real 1.5.2.3 traces show Tiles is useful
// as the engine's zero/nonzero movement sentinel while ordered steps are exposed by
// successive End changes as AP budget increases.
affordances._canonicalNeighbors <- function(_projection, _fromId, _toId)
{
    if (!(_fromId in _projection.runtime.tile_records)) return false;
    if (!(_toId in _projection.runtime.tile_records)) return false;
    local record = _projection.runtime.tile_records[_fromId];
    foreach (neighborId in record.neighbor_ids)
        if (neighborId == _toId) return true;
    return false;
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
    local lastTileId = legal.tileID(_active.getTile());
    local seen = {};
    seen[lastTileId] <- true;

    // Sweep the already-stored native path without executing travel. When the
    // affordable prefix End changes, that endpoint is the next native path step.
    // Validate adjacency against the canonical player-legal topology rather than
    // getDistanceTo(), whose square-coordinate distance is not path adjacency.
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

        local tileId = legal.tileID(prefix.End);
        if (tileId == lastTileId) continue;
        if (tileId in seen)
            throw "native movement prefix revisited an earlier path tile";
        if (!this._canonicalNeighbors(_projection, lastTileId, tileId))
            throw "native movement prefix endpoint is not a canonical adjacent tile";

        path.push(prefix.End);
        seen[tileId] <- true;
        lastTileId = tileId;
    }

    if (path.len() == 0)
        throw "native movement prefixes produced no ordered path steps";
    if (lastTileId != legal.tileID(_destination))
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
