local legal = ::BBAGENT_PlayerLegal;
local wire = ::BBAGENT_Wire;
local capture = ::BBAGENT_Capture;

// Some Battle Brothers actor instances expose inherited methods as callable
// members without making those methods discoverable through the Squirrel `in`
// operator. If the EntityManager-based compatibility build therefore yields no
// combatants for a command-ready state, rebuild only the actor-facing portion
// from the tactical turn list. Visibility and hidden-state filtering remain
// delegated to the existing PLAYER_LEGAL helpers.
local originalBuild = legal.build;
legal.build = function(_raw)
{
    local projection = originalBuild.acall([this, _raw]);
    if (projection == null
        || !("state" in projection)
        || !("combatants" in projection.state)
        || projection.state.combatants.len() != 0)
    {
        return projection;
    }

    local active = _raw.ActiveActor;
    if (active == null) return projection;

    local actors = [];
    local actorByRuntimeID = {};
    local visibleActorIds = {};
    local actorByTile = {};
    local current = _raw.TurnSequenceBar.getCurrentEntities();

    foreach (actor in current)
    {
        if (actor == null) continue;
        local actorLike = false;
        try
        {
            actor.isPlayerControlled();
            actor.isAlive();
            actor.isPlacedOnMap();
            actorLike = true;
        }
        catch (_error) {}
        if (!actorLike || !this._visibleToPlayer(actor)) continue;

        local projected = this._visibleActor(_raw, active, actor);
        actors.push(projected);
        actorByRuntimeID[actor.getID().tostring()] <- projected.actor_id;
        visibleActorIds[projected.actor_id] <- true;
        actorByTile[projected.position.value] <- projected.actor_id;
    }

    local memory = capture.getObservationMemory();
    foreach (key, fact in memory)
    {
        if (key.find("actor-memory:") != 0) continue;
        local actorId = fact.Value.actor_id;
        if (actorId in visibleActorIds) continue;
        actors.push(this._rememberedActor(fact));
    }
    actors.sort(@(a, b) a.actor_id <=> b.actor_id);

    foreach (tile in projection.state.tiles)
    {
        tile.occupant_actor_id = tile.tile_id in actorByTile
            ? actorByTile[tile.tile_id]
            : null;
    }

    local hostileFactions = {};
    local alliedFactions = {};
    foreach (actor in actors)
    {
        if (actor.faction.representation == "UNKNOWN") continue;
        local value = actor.faction.value;
        if (actor.relation == "HOSTILE") hostileFactions[value] <- true;
        else if (actor.relation == "ALLY") alliedFactions[value] <- true;
    }
    local hostile = [];
    local allied = [];
    foreach (id, _value in hostileFactions) hostile.push(id);
    foreach (id, _value in alliedFactions) allied.push(id);
    hostile.sort();
    allied.sort();

    local turnEntries = [];
    local maximum = _raw.TurnSequenceBar.m.MaxVisibleEntities;
    foreach (actor in current)
    {
        if (actor == null) continue;
        local runtimeId = null;
        try { runtimeId = actor.getID().tostring(); }
        catch (_error) { continue; }
        if (!(runtimeId in actorByRuntimeID)) continue;
        turnEntries.push({
            actor_id = actorByRuntimeID[runtimeId],
            done = wire.exactObserved(false),
            sequence = wire.exactObserved(turnEntries.len())
        });
        if (turnEntries.len() >= maximum) break;
    }

    projection.state.combatants = actors;
    projection.state.battle.hostile_faction_ids = hostile;
    projection.state.battle.allied_faction_ids = allied;
    projection.state.turn_state.entries = turnEntries;
    projection.runtime.actor_by_runtime_id = actorByRuntimeID;

    return projection;
};
