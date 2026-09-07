local affordances = ::BBAGENT_Affordances;
local legal = ::BBAGENT_PlayerLegal;
local oracle = ::BBAGENT_DebugOracle;
local sandbox = ::BBAGENT_CombatSandbox;

// If the real active brother has no ally-jump edge, try other player-controlled
// turn actors against the same player-legal projection. Local reachability may
// run more than once, but probeAllyJump performs native path/cost work only when
// an unresolved ally-jump edge exists, so this still produces at most one native
// sample for the battle generation.
oracle.probeAllyJumpAcrossOwnedRoster <- function(_raw, _projection)
{
    if (!this.Enabled) return null;
    local current = _raw.TurnSequenceBar.getCurrentEntities();
    local attempts = 0;

    foreach (actor in current)
    {
        if (actor == null) continue;
        local owned = false;
        try
        {
            owned = actor.isPlayerControlled()
                && actor.isAlive()
                && actor.isPlacedOnMap();
        }
        catch (_error) {}
        if (!owned) continue;
        ++attempts;

        local probeRaw = clone _raw;
        probeRaw.ActiveActor = actor;
        local probeProjection = clone _projection;
        probeProjection.runtime = clone _projection.runtime;
        probeProjection.runtime.active_actor = actor;
        probeProjection.runtime.active_actor_id = legal.actorID(actor);

        this.LastAllyJumpProbeKey = null;
        this.LastAllyJumpProbeRecord = null;
        try
        {
            affordances._movementReachability(probeRaw, probeProjection);
        }
        catch (_error)
        {
            continue;
        }

        local record = this.LastAllyJumpProbeRecord;
        if (record == null || !("candidate" in record) || !record.candidate)
            continue;
        record.probe_actor_id <- legal.actorID(actor);
        record.roster_probe_attempts <- attempts;
        return record;
    }

    this._allyJumpProbeStore(
        _raw,
        {
            candidate = false,
            reason = "no_candidate_across_owned_roster",
            roster_probe_attempts = attempts
        }
    );
    return this.LastAllyJumpProbeRecord;
};

local originalSandboxProcessJob = sandbox._processJob;
sandbox._processJob = function(_job)
{
    local wasPlayerLegalBuild = _job.kind == "player_legal_build";
    local ret = originalSandboxProcessJob.acall([this, _job]);
    if (!wasPlayerLegalBuild || this.State == null) return ret;
    if (this.State.player_legal_projection == null) return ret;

    local existing = oracle.LastAllyJumpProbeRecord;
    if (existing != null && "candidate" in existing && existing.candidate)
        return ret;

    local replacement = oracle.probeAllyJumpAcrossOwnedRoster(
        this.State.raw,
        this.State.player_legal_projection
    );
    if (replacement == null) return ret;

    foreach (job in this.State.jobs)
    {
        if (job.kind != "ally_jump_probe_record") continue;
        if (job.section != "debug_probe" || job.key != "ally_jump") continue;
        job.target = replacement;
        break;
    }
    return ret;
};
