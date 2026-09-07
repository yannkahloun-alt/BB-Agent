local affordances = ::BBAGENT_Affordances;

// Extend player-known occupancy with exact blocker observations from currently
// visible tiles only. Actor relations are overlaid afterward so a visible ally
// remains jumpable instead of collapsing into a generic blocker.
local baseVisibleOccupancy = affordances._movementVisibleOccupancy;
affordances._movementVisibleOccupancy = function(_projection)
{
    local ret = {};
    foreach (tile in _projection.state.tiles)
    {
        if (tile.blocking.representation != "EXACT") continue;
        if (!tile.blocking.value) continue;
        ret[tile.tile_id] <- "BLOCKED";
    }

    local actorOccupancy = baseVisibleOccupancy.acall([this, _projection]);
    foreach (tileId, kind in actorOccupancy)
        ret[tileId] <- kind;
    return ret;
};

local baseTransitionsFrom = affordances._movementTransitionsFrom;
affordances._movementTransitionsFrom = function(
    _active,
    _projection,
    _fromId,
    _tiles,
    _occupancy,
    _apCosts,
    _fatigueCosts
)
{
    local transitions = baseTransitionsFrom.acall([
        this,
        _active,
        _projection,
        _fromId,
        _tiles,
        _occupancy,
        _apCosts,
        _fatigueCosts
    ]);
    local ret = [];
    foreach (transition in transitions)
    {
        local landing = transition.landing_tile_id;
        local kind = landing in _occupancy ? _occupancy[landing] : null;
        if (kind == "BLOCKED") continue;
        ret.push(transition);
    }
    return ret;
};
