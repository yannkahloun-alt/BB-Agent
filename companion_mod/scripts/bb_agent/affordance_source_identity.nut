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
            local identity = item == null ? "empty" : item == -1 ? "blocked" : item.getID();
            ret.push(
                "active_item_slot=" + slotIndex + ":" + position + ":" + identity
            );
        }
    }
    ret.sort();
    return ret;
};

capture._fingerprintInputs = function(_state, _active)
{
    local ret = originalFingerprintInputs.acall([this, _state, _active]);
    foreach (token in this._activeItemSlotTopologyTokens(_active)) ret.push(token);
    ret.sort();
    return ret;
};
