local legal = ::BBAGENT_PlayerLegal;
local wire = ::BBAGENT_Wire;
local capture = ::BBAGENT_Capture;

// Tactical actor collections expose actor script objects directly. The pinned
// Battle Brothers runtime does not provide the removed lifetime method here, so
// preserve the final hardened projection while guarding only actual nulls.
legal.build = function(_raw)
{
    this._ensureBattle(_raw);
    local active = _raw.ActiveActor;
    local coords = this._coordinateMap();
    local actors = [];
    local actorByRuntimeID = {};
    local visibleActorIds = {};
    local actorByTile = {};

    local groups = _raw.EntityManager.getAllInstances();
    foreach (group in groups)
    {
        foreach (actor in group)
        {
            if (actor == null || !("isPlayerControlled" in actor)) continue;
            if (!this._visibleToPlayer(actor)) continue;
            local projected = this._visibleActor(_raw, active, actor);
            actors.push(projected);
            actorByRuntimeID[actor.getID().tostring()] <- projected.actor_id;
            visibleActorIds[projected.actor_id] <- true;
            actorByTile[projected.position.value] <- projected.actor_id;
        }
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

    local tileRecords = {};
    local tileVisible = {};
    local size = ::Tactical.getMapSize();
    for (local x = 0; x < size.X; x = ++x)
    {
        for (local y = 0; y < size.Y; y = ++y)
        {
            if (!::Tactical.isValidTileSquare(x, y)) continue;
            local tile = ::Tactical.getTileSquare(x, y);
            if (!tile.IsVisibleForPlayer) continue;
            local record = this._visibleTileRecord(_raw, tile, coords);
            tileRecords[record.tile_id] <- record;
            tileVisible[record.tile_id] <- true;
        }
    }
    memory = capture.getObservationMemory();
    foreach (key, fact in memory)
    {
        if (key.find("tile-memory:") != 0) continue;
        local record = fact.Value;
        if (!(record.tile_id in tileRecords)) tileRecords[record.tile_id] <- record;
    }

    local tiles = [];
    foreach (id, record in tileRecords)
        tiles.push(this._tileFromRecord(record, id in tileVisible, tileRecords, actorByTile));
    tiles.sort(@(a, b) a.tile_id <=> b.tile_id);

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
    hostile.sort(); allied.sort();

    // Preserve the hardening layer's visible-only compact turn presentation.
    local turnEntries = [];
    local current = _raw.TurnSequenceBar.getCurrentEntities();
    local maximum = _raw.TurnSequenceBar.m.MaxVisibleEntities;
    foreach (actor in current)
    {
        if (actor == null) continue;
        local runtimeId = actor.getID().tostring();
        if (!(runtimeId in actorByRuntimeID)) continue;
        turnEntries.push({
            actor_id = actorByRuntimeID[runtimeId],
            done = wire.exactObserved(false),
            sequence = wire.exactObserved(turnEntries.len())
        });
        if (turnEntries.len() >= maximum) break;
    }

    local activeId = this.actorID(active);
    return {
        state = {
            contract_version = wire.KernelIdentity.tactical_state,
            state_id = "",
            raw_capture_id = null,
            information_profile = "player_legal",
            ruleset = {
                game_version = capture.SupportedGameVersion,
                content_fingerprint = capture.RulesetContentFingerprint,
                mods = []
            },
            battle = {
                battle_id = "live-battle:" + _raw.BattleSequence,
                player_faction_id = "faction:" + active.getFaction(),
                phase = "COMBAT",
                hostile_faction_ids = hostile,
                allied_faction_ids = allied,
                flags = []
            },
            decision = {
                active_actor_id = activeId,
                round = _raw.ValidationContext.Round,
                decision_index = _raw.SourceGeneration,
                actor_has_waited = active.isWaitActionSpent(),
                actor_may_wait = _raw.TurnSequenceBar.canEntityWait(active) && active.isAbleToWait(),
                turn_phase = "command_ready",
                prior_action_ids = []
            },
            turn_state = { entries = turnEntries },
            environment = { light = "unknown", weather = null, effect_ids = [] },
            tiles = tiles,
            combatants = actors,
            action_affordances = null,
            ground_entities = [],
            annotations = null
        },
        runtime = {
            active_actor = active,
            active_actor_id = activeId,
            actor_by_runtime_id = actorByRuntimeID,
            tile_records = tileRecords,
            tile_visible = tileVisible
        }
    };
};
