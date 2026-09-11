local sandbox = ::BBAGENT_CombatSandbox;

// Freeze the independent PLAYER_LEGAL projection at the decision boundary. The
// raw acquisition deliberately contains live runtime references; rebuilding from
// them after the long oracle queue drains can observe a later visibility state
// while still claiming the original source generation. Publication remains
// oracle-first: the captured projection is not enqueued or serialized until the
// omniscient queue has drained.
local originalBegin = sandbox.begin;
sandbox.begin = function(_raw)
{
    originalBegin.acall([this, _raw]);
    if (this.State == null) return;

    this.State.player_legal_projection = null;
    this.State.player_legal_projection_error <- null;
    try
    {
        this.State.player_legal_projection = ::BBAGENT_PlayerLegal.build(_raw);
    }
    catch (error)
    {
        this.State.player_legal_projection_error = error.tostring();
    }

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

    local ret = null;
    if (wasPlayerLegalBuild && this.State != null)
    {
        if (this.State.player_legal_projection != null)
        {
            this._enqueueProjectionRecords(this.State.player_legal_projection);
        }
        else
        {
            this._enqueue(
                "player_legal_meta",
                "player_legal_meta",
                "root",
                {
                    __capture_error = this.State.player_legal_projection_error,
                    job_kind = _job.kind
                }
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
    + " snapshot=decision_boundary release=oracle_queue_drained"
    + " manifest_after_player_legal=true"
);
