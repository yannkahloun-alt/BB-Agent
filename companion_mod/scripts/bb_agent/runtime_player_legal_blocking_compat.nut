local legal = ::BBAGENT_PlayerLegal;
local wire = ::BBAGENT_Wire;

// Produce a player-legal blocker bit only for a currently visible tile. A
// hidden actor is deliberately treated as absent from the player-known graph;
// visible actors and visible non-actor tactical entities block normally.
legal._visibleTileBlocking <- function(_tile)
{
    if (_tile.IsEmpty) return false;

    local entity = null;
    try { entity = _tile.getEntity(); } catch (_error) { return true; }
    if (entity == null) return true;

    if ("isPlayerControlled" in entity)
    {
        try
        {
            if (entity.isPlayerControlled()) return true;
            if (entity.isHiddenToPlayer()) return false;
            return true;
        }
        catch (_error)
        {
            // Failing closed here would leak a hidden blocker. Unknown actor
            // visibility therefore stays absent from the player-known graph.
            return false;
        }
    }

    return true;
};

local originalVisibleTileRecord = legal._visibleTileRecord;
legal._visibleTileRecord = function(_raw, _tile, _coords)
{
    local record = originalVisibleTileRecord.acall([this, _raw, _tile, _coords]);
    record.blocking <- this._visibleTileBlocking(_tile);
    return record;
};

local originalTileFromRecord = legal._tileFromRecord;
legal._tileFromRecord = function(_record, _visible, _included, _actorIds)
{
    local tile = originalTileFromRecord.acall([
        this,
        _record,
        _visible,
        _included,
        _actorIds
    ]);
    if (_visible && "blocking" in _record)
        tile.blocking = wire.exactObserved(_record.blocking);
    else
        tile.blocking = wire.unknownValue();
    return tile;
};
