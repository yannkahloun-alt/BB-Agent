local legal = ::BBAGENT_PlayerLegal;
local wire = ::BBAGENT_Wire;
local capture = ::BBAGENT_Capture;

// Legal observation memory must not retain raw internal faction IDs for
// non-owned actors. Until a player-facing faction/archetype mapping exists,
// relation is exported but non-owned faction identity remains UNKNOWN.
local originalRemember = capture.rememberPlayerLegalFact;
capture.rememberPlayerLegalFact = function(_key, _value, _round, _decision)
{
    if (_key.find("actor-memory:") == 0 && typeof _value == "table" && "faction" in _value)
    {
        local sanitized = clone _value;
        delete sanitized.faction;
        return originalRemember.acall([this, _key, sanitized, _round, _decision]);
    }
    return originalRemember.acall([this, _key, _value, _round, _decision]);
}

local originalVisibleActor = legal._visibleActor;
legal._visibleActor = function(_raw, _active, _actor)
{
    local projected = originalVisibleActor.acall([this, _raw, _active, _actor]);
    if (!projected.is_player_controlled) projected.faction = wire.unknownValue();
    return projected;
}

legal._rememberedActor = function(_fact)
{
    local value = _fact.Value;
    return {
        actor_id = value.actor_id,
        relation = value.relation,
        is_player_controlled = false,
        life_state = "ALIVE",
        visible = false,
        position = wire.unknownValue(),
        resources = this._unknownResources(),
        faction = wire.unknownValue(),
        content_identity = wire.unknownValue(),
        equipment = [], effects = [], skills = [], tactical_stats = [],
        perks = wire.unknownValue(), traits = wire.unknownValue(),
        last_seen = {
            tile_id = value.tile_id,
            observed_at = { round = _fact.ObservedRound, decision = _fact.ObservedDecision }
        }
    };
}

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
