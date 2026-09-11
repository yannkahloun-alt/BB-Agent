local sandbox = ::BBAGENT_CombatSandbox;

local wire = ::BBAGENT_Wire;

// PLAYER_LEGAL publication remains deferred until the oracle queue drains. The
// capture substrate records the small set of visible non-owned actor facts while
// its existing entity fingerprint pass is already visiting those actors. This
// preserves decision-boundary visibility without adding another synchronous
// entity or map traversal to DECISION_READY.
local originalBegin = sandbox.begin;
sandbox.begin = function(_raw)
{
    local priorState = this.State;
    originalBegin.acall([this, _raw]);
    if (this.State == null || this.State == priorState) return;

    local filtered = [];
    foreach (job in this.State.jobs)
    {
        if (job.kind == "player_legal_build") continue;
        filtered.push(job);
    }
    this.State.jobs = filtered;
    this.State.player_legal_phase_scheduled <- false;
    this.State.player_legal_phase_complete <- false;
};

sandbox._reconcileBoundaryActors <- function(_projection, _raw)
{
    if (!("PlayerVisibleNonOwnedActors" in _raw)) return _projection;

    // The deferred legacy builder may have observed a later frame. Discard any
    // memory writes it made and resume from the decision-boundary memory copy.
    if ("PlayerLegalObservationMemory" in _raw)
        ::BBAGENT_Capture.State.ObservationMemory =
            ::BBAGENT_Capture._copyPlayerLegalMemoryValue(
                _raw.PlayerLegalObservationMemory
            );

    local actors = [];
    local visibleActorIds = {};
    local actorByRuntimeID = {};
    local actorByTile = {};
    foreach (actor in _projection.state.combatants)
    {
        if (!actor.is_player_controlled) continue;
        actors.push(actor);
        visibleActorIds[actor.actor_id] <- true;
        if (actor.position.representation == "EXACT_OBSERVED")
            actorByTile[actor.position.value] <- actor.actor_id;
    }

    foreach (fact in _raw.PlayerVisibleNonOwnedActors)
    {
        local actor = {
            actor_id = fact.actor_id,
            relation = fact.relation,
            is_player_controlled = false,
            life_state = "ALIVE",
            visible = true,
            position = wire.exactObserved(fact.tile_id),
            resources = ::BBAGENT_PlayerLegal._unknownResources(),
            faction = wire.unknownValue(),
            content_identity = wire.unknownValue(),
            equipment = [], effects = [], skills = [], tactical_stats = [],
            perks = wire.unknownValue(), traits = wire.unknownValue(),
            last_seen = null
        };
        actors.push(actor);
        visibleActorIds[fact.actor_id] <- true;
        actorByRuntimeID[fact.runtime_id] <- fact.actor_id;
        actorByTile[fact.tile_id] <- fact.actor_id;
        ::BBAGENT_Capture.rememberPlayerLegalFact(
            "actor-memory:" + fact.actor_id,
            { actor_id = fact.actor_id, relation = fact.relation, tile_id = fact.tile_id },
            _raw.ValidationContext.Round,
            _raw.SourceGeneration
        );
    }

    foreach (key, memoryFact in ::BBAGENT_Capture.getObservationMemory())
    {
        if (key.find("actor-memory:") != 0) continue;
        if (memoryFact.Value.actor_id in visibleActorIds) continue;
        actors.push(::BBAGENT_PlayerLegal._rememberedActor(memoryFact));
    }
    actors.sort(@(a, b) a.actor_id <=> b.actor_id);

    foreach (tile in _projection.state.tiles)
        tile.occupant_actor_id = tile.tile_id in actorByTile ? actorByTile[tile.tile_id] : null;

    _projection.state.combatants = actors;
    foreach (runtimeID, actorID in _projection.runtime.actor_by_runtime_id)
        if (actorID in visibleActorIds) actorByRuntimeID[runtimeID] <- actorID;
    _projection.runtime.actor_by_runtime_id = actorByRuntimeID;
    return _projection;
};

local originalProcessJob = sandbox._processJob;
sandbox._processJob = function(_job)
{
    local wasPlayerLegalBuild = _job.kind == "player_legal_build";
    if (wasPlayerLegalBuild && this.State != null)
    {
        ::logInfo(
            "[BB-Agent Combat Sandbox] player_legal_build_begin"
            + " battle=" + this.State.battle_sequence.tostring()
            + " generation=" + this.State.source_generation.tostring()
        );
    }

    local ret = null;
    if (wasPlayerLegalBuild && this.State != null)
    {
        try
        {
            local projection = ::BBAGENT_PlayerLegal.build(this.State.raw);
            projection = this._reconcileBoundaryActors(projection, this.State.raw);
            this.State.player_legal_projection = projection;
            this._enqueueProjectionRecords(projection);
        }
        catch (error)
        {
            this._enqueue(
                "player_legal_meta",
                "player_legal_meta",
                "root",
                { __capture_error = error.tostring(), job_kind = _job.kind }
            );
        }
    }
    else
    {
        ret = originalProcessJob.acall([this, _job]);
    }
    if (wasPlayerLegalBuild && this.State != null)
    {
        this.State.player_legal_phase_complete = true;
        ::logInfo(
            "[BB-Agent Combat Sandbox] player_legal_build_end"
            + " battle=" + this.State.battle_sequence.tostring()
            + " generation=" + this.State.source_generation.tostring()
        );
    }
    return ret;
};

local originalEnqueueManifestJobs = sandbox._enqueueManifestJobs;
sandbox._enqueueManifestJobs = function()
{
    if (this.State == null) return;
    if (!this.State.player_legal_phase_complete)
    {
        if (!this.State.player_legal_phase_scheduled)
        {
            this.State.player_legal_phase_scheduled = true;
            this._enqueue("player_legal_build", null, null, null, null, false);
            ::logInfo(
                "[BB-Agent Combat Sandbox] player_legal_phase_released"
                + " battle=" + this.State.battle_sequence.tostring()
                + " generation=" + this.State.source_generation.tostring()
                + " oracle_jobs_drained=true"
            );
        }
        return;
    }
    return originalEnqueueManifestJobs.acall([this]);
};

::logInfo(
    "[BB-Agent Combat Sandbox] player_legal_phase_loaded"
    + " actor_visibility=decision_boundary release=oracle_queue_drained"
    + " manifest_after_player_legal=true"
);
