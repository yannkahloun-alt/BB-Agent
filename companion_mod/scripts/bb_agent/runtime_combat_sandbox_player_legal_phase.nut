local sandbox = ::BBAGENT_CombatSandbox;

// Enforce a true two-phase sandbox lifecycle. The earlier oracle-first layer only
// moved player_legal_build to the end of the seed queue, but incremental discovery
// appends follow-up jobs behind that seed entry. Remove the build job entirely at
// begin(), then release it only when the omniscient queue has actually drained.
// Manifest finalization is allowed only after the PLAYER_LEGAL phase has executed
// and all records it enqueued have drained too.
local originalBegin = sandbox.begin;
sandbox.begin = function(_raw)
{
    originalBegin.acall([this, _raw]);
    if (this.State == null) return;

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

    local ret = originalProcessJob.acall([this, _job]);
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
    + " release=oracle_queue_drained manifest_after_player_legal=true"
);
