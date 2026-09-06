local capture = ::BBAGENT_Capture;

// Tactical.Entities.getAllInstances() exposes the live actor arrays directly.
// These entries are actor script objects, not weakrefs; mirror the pinned game
// scripts and guard only actual null entries before reading actor methods.
capture._entityTokens = function()
{
    local ret = [];
    local groups = ::Tactical.Entities.getAllInstances();
    foreach (group in groups)
    {
        foreach (actor in group)
        {
            if (actor == null) continue;
            ret.push(this._actorToken(actor));
        }
    }
    ret.sort();
    return ret;
};

capture._turnSequenceTokens = function()
{
    local ret = [];
    local entities = ::Tactical.TurnSequenceBar.getCurrentEntities();
    foreach (index, actor in entities)
    {
        if (actor == null) continue;
        ret.push("turn=" + index + ":" + actor.getID());
    }
    return ret;
};
