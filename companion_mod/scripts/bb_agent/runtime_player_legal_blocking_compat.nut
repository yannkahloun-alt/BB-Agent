local legal = ::BBAGENT_PlayerLegal;
local wire = ::BBAGENT_Wire;

// Issue #98 / pinned tactical_state.nut authority:
// path selection may use current occupancy for a tile that is visible to the
// player, while non-visible actor occupancy is ignored. _visibleTileRecord is
// called only for IsVisibleForPlayer tiles, so IsEmpty is player-facing here and
// no entity identity or hidden-state query is required.
local originalVisibleTileRecord = legal._visibleTileRecord;
legal._visibleTileRecord = function(_raw, _tile, _coords)
{
    local record = originalVisibleTileRecord.acall([this, _raw, _tile, _coords]);
    record.blocking <- !_tile.IsEmpty;
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
