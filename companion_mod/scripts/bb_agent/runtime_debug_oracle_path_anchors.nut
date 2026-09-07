local oracle = ::BBAGENT_DebugOracle;
local legal = ::BBAGENT_PlayerLegal;
local originalCostSummary = oracle._costSummary;

oracle._anchorTileID <- function(_costs, _name)
{
    if (_costs == null || !(_name in _costs) || _costs[_name] == null)
        return "null";
    try
    {
        return legal.tileID(_costs[_name]);
    }
    catch (_error)
    {
        return "unreadable";
    }
};

oracle._costSummary = function(_costs)
{
    local summary = originalCostSummary.acall([this, _costs]);
    if (_costs == null) return summary;
    return summary
        + " first=" + this._anchorTileID(_costs, "First")
        + " second_last=" + this._anchorTileID(_costs, "SecondLastBeforeEnd")
        + " last=" + this._anchorTileID(_costs, "LastBeforeEnd");
};

// 0.2.15 already proved these native/private navigator members are unavailable.
// Keep the next diagnostic bounded around the engine-supplied path anchors.
oracle._dumpCostFields = function(_label, _costs)
{
};

oracle._probeNavigatorInternals = function(_navigator)
{
};
