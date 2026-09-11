local affordances = ::BBAGENT_Affordances;
local legal = ::BBAGENT_PlayerLegal;

affordances.CurrentProjection <- null;

// A native movement command is exportable only when every resolved path step
// already exists in the player-legal canonical map. Hidden raw map access must
// not be used as an implicit path-only escape hatch.
local originalNavigatorPath = affordances._navigatorPath;
affordances._navigatorPathForProjection <- function(
    _navigator,
    _origin,
    _destination,
    _projection
)
{
    local path = originalNavigatorPath.acall([this, _navigator, _origin, _destination]);
    if (_projection == null)
        throw "movement path validation has no player-legal projection";
    foreach (tile in path)
    {
        local tileId = legal.tileID(tile);
        if (!(tileId in _projection.runtime.tile_records))
            throw "native movement path leaves the player-legal canonical map";
    }
    return path;
}

affordances._navigatorPath = function(_navigator, _origin, _destination)
{
    return this._navigatorPathForProjection(
        _navigator,
        _origin,
        _destination,
        this.CurrentProjection
    );
}

local originalAcquire = affordances.acquire;
affordances.acquire = function(_raw, _projection)
{
    this.CurrentProjection = _projection;
    try
    {
        local actions = originalAcquire.acall([this, _raw, _projection]);
        this.CurrentProjection = null;
        return actions;
    }
    catch (error)
    {
        this.CurrentProjection = null;
        throw error;
    }
}
