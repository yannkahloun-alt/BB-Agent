local capture = ::BBAGENT_Capture;
local originalFingerprintInputs = capture._fingerprintInputs;

// EQUIP_ITEM command identity can depend on exact source/target bag positions,
// while item.getCurrentSlotType() only distinguishes the broad slot type. Keep
// the active player's nested item-container topology in the raw source identity
// without invoking any mutating equip/swap/action-cost operation.
capture._activeItemSlotTopologyTokens <- function(_active)
{
    local ret = [];
    foreach (slotIndex, slotItems in _active.getItems().m.Items)
    {
        foreach (position, item in slotItems)
        {
            local slotPrefix = "active_item_slot=" + slotIndex + ":" + position;
            if (item == null)
            {
                ret.push(slotPrefix + ":empty");
                continue;
            }
            if (item == -1)
            {
                ret.push(slotPrefix + ":blocked");
                continue;
            }

            local itemPrefix = slotPrefix + ":item=" + item.getID();
            ret.push(itemPrefix + ":condition=" + item.getCondition());
            foreach (
                stateToken in this._primitiveStateTokens(
                    itemPrefix + ":m",
                    item.m
                )
            )
                ret.push(stateToken);
        }
    }
    ret.sort();
    return ret;
};

// Tile effects are canonical #52 source facts and can alter tactical semantics
// while level/type/subtype/occupancy remain unchanged. Replace the substrate's
// map tokenizer rather than scanning the map a second time. Effect tables carry
// stable primitive identity/lifetime fields plus callbacks; the primitive filter
// deliberately ignores functions and opaque engine objects.
capture._mapTokens = function()
{
    local ret = [];
    local size = ::Tactical.getMapSize();
    for (local x = 0; x < size.X; x = ++x)
    {
        for (local y = 0; y < size.Y; y = ++y)
        {
            if (!::Tactical.isValidTileSquare(x, y)) continue;
            local tile = ::Tactical.getTileSquare(x, y);
            ret.push(
                "map=" + x + ":" + y
                + ":level=" + tile.Level
                + ":type=" + tile.Type
                + ":subtype=" + tile.Subtype
                + ":empty=" + this._boolToken(tile.IsEmpty)
                + ":visible=" + this._boolToken(tile.IsVisibleForPlayer)
                + ":discovered=" + this._boolToken(tile.IsDiscovered)
            );
            if (tile.Properties.Effect == null) continue;
            foreach (
                effectToken in this._primitiveStateTokens(
                    "tile_effect=" + x + ":" + y,
                    tile.Properties.Effect
                )
            )
                ret.push(effectToken);
        }
    }
    ret.sort();
    return ret;
};

capture._fingerprintInputs = function(_state, _active)
{
    local ret = originalFingerprintInputs.acall([this, _state, _active]);
    ret.push(this._arrayToken("active_allied_factions", _active.getAlliedFactions()));
    foreach (token in this._activeItemSlotTopologyTokens(_active)) ret.push(token);
    ret.sort();
    return ret;
};
