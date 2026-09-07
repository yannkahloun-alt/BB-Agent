local sandbox = ::BBAGENT_CombatSandbox;
local capture = ::BBAGENT_Capture;
local oracle = ::BBAGENT_DebugOracle;

// Normal live export deliberately latches a failed READY signature and clears
// CurrentRaw until the game source changes. The forensic dump must outlive that
// failure, because its purpose is to capture the state that made normal export
// fail. Keep a separate source-signature identity and gate progress directly on
// command readiness + capture generation instead of getCurrentRawAcquisition().
local originalBegin = sandbox.begin;
sandbox.begin = function(_raw)
{
    originalBegin.acall([this, _raw]);
    if (this.State == null) return;
    if (this.State.battle_sequence != _raw.BattleSequence
        || this.State.source_generation != _raw.SourceGeneration)
    {
        return;
    }
    if (!("source_signature" in this.State))
        this.State.source_signature <- capture.State.LastReadySignature;
};

sandbox.pump = function()
{
    if (!oracle.Enabled || this.State == null) return;

    // Battle/generation are authoritative even if normal READY was latched off.
    if (capture.State.BattleSequence != this.State.battle_sequence
        || capture.State.SourceGeneration != this.State.source_generation)
    {
        this.cancel("generation_changed");
        return;
    }

    // Do not read a moving/action/modal state. Pausing is correct here: observe()
    // will update LastReadySignature/SourceGeneration before the next READY pump.
    local readiness = capture._commandReadiness(this.State.raw.TacticalState);
    if (!readiness.Ready) return;

    if (capture.State.LastReadySignature != this.State.source_signature)
    {
        this.cancel("generation_changed");
        return;
    }

    local processed = 0;
    while (processed < this.RecordsPerPump && this.State != null)
    {
        if (this.State.cursor >= this.State.jobs.len())
        {
            if (!this.State.finalizing)
            {
                this._enqueueManifestJobs();
                continue;
            }
            break;
        }

        local job = this.State.jobs[this.State.cursor];
        ++this.State.cursor;
        try
        {
            this._processJob(job);
        }
        catch (error)
        {
            if (job.section == null || job.key == null)
            {
                ::logError(
                    "[BB-Agent Combat Sandbox] job_error kind=" + job.kind
                    + " error=" + error.tostring()
                );
            }
            else
            {
                try { this._emitJobError(job, error); }
                catch (transportError)
                {
                    ::logError(
                        "[BB-Agent Combat Sandbox] transport_error kind=" + job.kind
                        + " error=" + transportError.tostring()
                    );
                    this.cancel("transport_error");
                    return;
                }
            }
        }
        ++processed;

        if (this.State != null && this.State.cursor % 64 == 0)
        {
            ::logInfo(
                "[BB-Agent Combat Sandbox] progress battle="
                + this.State.battle_sequence.tostring()
                + " generation=" + this.State.source_generation.tostring()
                + " cursor=" + this.State.cursor.tostring()
                + " jobs=" + this.State.jobs.len().tostring()
            );
        }
    }
};

::logInfo(
    "[BB-Agent Combat Sandbox] continuity_loaded survives_failed_ready=true"
);
