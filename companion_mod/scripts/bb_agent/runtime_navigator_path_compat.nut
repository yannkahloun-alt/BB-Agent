local affordances = ::BBAGENT_Affordances;
local legal = ::BBAGENT_PlayerLegal;

// Diagnostic smoke build: capture the actual Battle Brothers navigator prefix
// semantics before attempting any further path reconstruction fix.
affordances.NavigatorPrefixTraceCaptured <- false;

affordances._traceNavigatorPrefixes <- function(
    _navigator,
    _active,
    _settings,
    _costs,
    _destination
)
{
    if (this.NavigatorPrefixTraceCaptured) return;
    this.NavigatorPrefixTraceCaptured = true;

    local destinationId = legal.tileID(_destination);
    local originId = legal.tileID(_active.getTile());
    local fullTiles = "missing";
    local fullEnd = "null";
    local fullComplete = "missing";
    local fullAp = "missing";
    local fullFat = "missing";

    if ("Tiles" in _costs) fullTiles = _costs.Tiles.tostring();
    if ("End" in _costs && _costs.End != null) fullEnd = legal.tileID(_costs.End);
    if ("IsComplete" in _costs) fullComplete = _costs.IsComplete.tostring();
    if ("ActionPointsRequired" in _costs) fullAp = _costs.ActionPointsRequired.tostring();
    else if ("ActionPoints" in _costs) fullAp = _costs.ActionPoints.tostring();
    if ("FatigueRequired" in _costs) fullFat = _costs.FatigueRequired.tostring();
    else if ("Fatigue" in _costs) fullFat = _costs.Fatigue.tostring();

    ::logInfo(
        "[BB-Agent PathTrace] origin=" + originId
        + " destination=" + destinationId
        + " full_tiles=" + fullTiles
        + " full_end=" + fullEnd
        + " full_complete=" + fullComplete
        + " full_ap=" + fullAp
        + " full_fat=" + fullFat
    );

    local apRequired = this._movementCost(
        _costs,
        "ActionPointsRequired",
        "ActionPoints"
    );
    local fatigueAvailable = _active.getFatigueMax() - _active.getFatigue();

    for (local apBudget = 0; apBudget <= apRequired; apBudget = ++apBudget)
    {
        local prefix = _navigator.getCostForPath(
            _active,
            _settings,
            apBudget,
            fatigueAvailable
        );
        local tiles = "missing";
        local endId = "null";
        local complete = "missing";
        local ap = "missing";
        local fat = "missing";

        if ("Tiles" in prefix) tiles = prefix.Tiles.tostring();
        if ("End" in prefix && prefix.End != null) endId = legal.tileID(prefix.End);
        if ("IsComplete" in prefix) complete = prefix.IsComplete.tostring();
        if ("ActionPointsRequired" in prefix) ap = prefix.ActionPointsRequired.tostring();
        else if ("ActionPoints" in prefix) ap = prefix.ActionPoints.tostring();
        if ("FatigueRequired" in prefix) fat = prefix.FatigueRequired.tostring();
        else if ("Fatigue" in prefix) fat = prefix.Fatigue.tostring();

        ::logInfo(
            "[BB-Agent PathTrace] budget=" + apBudget
            + " tiles=" + tiles
            + " end=" + endId
            + " complete=" + complete
            + " ap=" + ap
            + " fat=" + fat
        );
    }
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
    this._traceNavigatorPrefixes(
        _navigator,
        _active,
        _settings,
        _costs,
        _destination
    );
    throw "navigator prefix trace captured; diagnostic build remains fail-closed";
};

// Preserve movement discovery/costing exactly long enough to reach one native
// complete path and record its prefix behavior. No command is executed.
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
                if ("Tiles" in costs && costs.Tiles != 0
                    && "IsComplete" in costs && costs.IsComplete)
                {
                    pathTiles = this._nativeCostPrefixPath(
                        navigator,
                        active,
                        settings,
                        costs,
                        destination,
                        _projection
                    );
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
        if (!found || costs == null || pathTiles == null) continue;

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
