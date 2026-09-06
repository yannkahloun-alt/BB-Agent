local legal = ::BBAGENT_PlayerLegal;
local wire = ::BBAGENT_Wire;

// Keep the exported turn presentation conservative even though the raw capture
// can see every tactical entity. Hidden raw entries neither appear nor create
// sequence-number gaps in player_legal state.
legal._visibleToPlayer = function(_actor)
{
    if (!_actor.isAlive() || !_actor.isPlacedOnMap()) return false;
    if (_actor.isPlayerControlled()) return true;
    return !_actor.isHiddenToPlayer() && _actor.getTile().IsVisibleForPlayer;
}

local originalBuild = legal.build;
legal.build = function(_raw)
{
    local projection = originalBuild.acall([this, _raw]);
    local entries = [];
    local current = _raw.TurnSequenceBar.getCurrentEntities();
    local maximum = _raw.TurnSequenceBar.m.MaxVisibleEntities;
    foreach (actor in current)
    {
        if (actor == null || actor.isNull()) continue;
        local runtimeId = actor.getID().tostring();
        if (!(runtimeId in projection.runtime.actor_by_runtime_id)) continue;
        entries.push({
            actor_id = projection.runtime.actor_by_runtime_id[runtimeId],
            done = wire.exactObserved(false),
            sequence = wire.exactObserved(entries.len())
        });
        if (entries.len() >= maximum) break;
    }
    projection.state.turn_state.entries = entries;
    return projection;
}
