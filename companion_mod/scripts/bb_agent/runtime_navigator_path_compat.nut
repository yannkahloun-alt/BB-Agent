local affordances = ::BBAGENT_Affordances;
local legal = ::BBAGENT_PlayerLegal;

// Pinned Battle Brothers scripts 162f498ac7c49b4c317bbf54718a595ecef6a65a
// expose tactical paths through the stored navigator path plus getCostForPath()
// prefix summaries (Tiles/End/IsComplete), not through a script getPath accessor.
// Live 1.5.2.3 evidence shows nonzero Tiles counts stored path nodes including
// the origin, so canonical movement-step count is Tiles - 1.
affordances._nativeMovementStepCount <- function(_tiles)
{
    if (typeof _tiles != "integer" || _tiles < 0)
        throw "native movement preview returned an invalid path tile count";
    if (_tiles == 0) return 0;
    if (_tiles < 2)
        throw "native movement path node count cannot represent a movement step";
    return _tiles - 1;
};

// Reconstruct only complete, currently affordable command paths and never travel.
affordances._nativeCostPrefixPath <- function(
    _navigator,
    _active,
    _settings,
    _costs,
    _destination,
    _projection
)
{
    if (!("Tiles" in _costs))
        throw "native movement preview returned no path node count";
    local targetSteps = this._nativeMovementStepCount(_costs.Tiles);
    if (targetSteps <= 0)
        throw "native movement preview returned no movement steps";
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
    local observedSteps = 0;

    // Movement AP cost is positive per step. Increasing the AP budget over the
    // already-stored native path exposes each successive path prefix endpoint.
    // Native Tiles is a node count including origin, so normalize before comparing.
    for (local apBudget = 1; apBudget <= apRequired; apBudget = ++apBudget)
    {
        local prefix = _navigator.getCostForPath(
            _active,
            _settings,
            apBudget,
            fatigueAvailable
        );
        if (!("Tiles" in prefix))
            throw "native movement prefix returned no path node count";
        local prefixSteps = this._nativeMovementStepCount(prefix.Tiles);
        if (prefixSteps < observedSteps || prefixSteps > targetSteps)
            throw "native movement prefix step count is not monotonic";
        if (prefixSteps == observedSteps) continue;
        if (prefixSteps != observedSteps + 1)
            throw "native movement prefix skipped an ordered path step";
        if (!("End" in prefix) || prefix.End == null)
            throw "native movement prefix advanced without an endpoint";

        local tileId = legal.tileID(prefix.End);
        if (!(tileId in _projection.runtime.tile_records))
            throw "native movement path leaves the player-legal canonical map";
        path.push(prefix.End);
        observedSteps = prefixSteps;
    }

    if (observedSteps != targetSteps || path.len() != targetSteps)
        throw "native movement path prefixes did not reconstruct every path step";
    if (legal.tileID(path[path.len() - 1]) != legal.tileID(_destination))
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
                if (!("Tiles" in costs))
                    throw "native movement preview returned no path node count";
                local steps = this._nativeMovementStepCount(costs.Tiles);
                if (!("IsComplete" in costs) || typeof costs.IsComplete != "bool")
                    throw "native movement preview did not expose path completeness";
                if (steps != 0 && costs.IsComplete)
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
