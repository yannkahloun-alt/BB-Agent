local affordances = ::BBAGENT_Affordances;

// Bounded DEBUG_ORACLE observation from the full combat sandbox established
// the native resource rule for passing over exactly one allied unit:
//
//   native path tiles: ally tile, landing tile
//   native cost: sum(from -> ally, ally -> landing)
//
// Keep topology in runtime_movement_graph_compat and resolve only the resource
// cost here so the observation cannot leak any omniscient state into production.
local originalTransitionsFrom = affordances._movementTransitionsFrom;
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
    local transitions = originalTransitionsFrom.acall([
        this,
        _active,
        _projection,
        _fromId,
        _tiles,
        _occupancy,
        _apCosts,
        _fatigueCosts
    ]);

    if (!(_fromId in _tiles)) return transitions;
    local fromTile = _tiles[_fromId];

    foreach (transition in transitions)
    {
        if (transition.kind != "ALLY_JUMP") continue;
        if (!(transition.via_tile_id in _tiles)) continue;

        local allyTile = _tiles[transition.via_tile_id];
        local first = this._movementStepCosts(
            _active,
            fromTile,
            allyTile,
            _apCosts,
            _fatigueCosts
        );
        local second = this._movementStepCosts(
            _active,
            allyTile,
            transition.landing_tile,
            _apCosts,
            _fatigueCosts
        );
        if (first == null || second == null) continue;

        transition.step = {
            ap = first.ap + second.ap,
            path_fatigue = first.path_fatigue + second.path_fatigue,
            execution_fatigue = first.execution_fatigue + second.execution_fatigue
        };
        transition.resource_cost_resolved = true;
    }

    return transitions;
};
