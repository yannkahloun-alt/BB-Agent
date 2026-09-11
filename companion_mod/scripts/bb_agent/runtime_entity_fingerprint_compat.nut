local capture = ::BBAGENT_Capture;

// Tactical.Entities.getAllInstances() exposes the live actor arrays directly.
// These entries are actor script objects, not weakrefs; mirror the pinned game
// scripts and guard only actual null entries before reading actor methods.
capture._entityTokens = function()
{
    local ret = [];
    local visibleNonOwned = [];
    local groups = ::Tactical.Entities.getAllInstances();
    foreach (group in groups)
    {
        foreach (actor in group)
        {
            if (actor == null) continue;
            ret.push(this._actorToken(actor));
            try
            {
                if (!actor.isPlayerControlled()
                    && actor.isAlive()
                    && actor.isPlacedOnMap()
                    && !actor.isHiddenToPlayer()
                    && actor.getTile().IsVisibleForPlayer)
                {
                    visibleNonOwned.push({
                        actor_id = "actor:" + actor.getID(),
                        runtime_id = actor.getID().tostring(),
                        relation = ::Tactical.TurnSequenceBar.getActiveEntity().isAlliedWith(actor)
                            ? "ALLY"
                            : "HOSTILE",
                        tile_id = "tile:" + actor.getTile().SquareCoords.X
                            + ":" + actor.getTile().SquareCoords.Y
                    });
                }
            }
            catch (_error) {}
        }
    }
    ret.sort();
    visibleNonOwned.sort(@(a, b) a.actor_id <=> b.actor_id);
    this.State.PendingPlayerVisibleNonOwnedActors = visibleNonOwned;
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
