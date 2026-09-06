local capture = ::BBAGENT_Capture;
local liveExport = ::BBAGENT_LiveExport;

// A failed canonical READY export must remain fail-closed for the exact source
// signature that failed. Re-arm only after the observed source actually changes.
capture.FailedReadySignature <- null;

local originalBeginBattle = capture.beginBattle;
capture.beginBattle = function()
{
    this.FailedReadySignature = null;
    return originalBeginBattle.acall([this]);
};

capture._latchCurrentReadyFailure <- function()
{
    if (!this.State.IsReady || this.State.LastReadySignature == null) return;
    this.FailedReadySignature = this.State.LastReadySignature;
};

// Preserve #70 diagnostics and the existing capture lifecycle while making
// invalidation delivery one-shot and suppressing retries of an unchanged failed
// READY signature.
capture.observe = function(_state)
{
    local stage = "readiness";
    try
    {
        local readiness = this._commandReadiness(_state);
        if (!readiness.Ready)
        {
            if (!this.State.IsReady) return null;
            return this.invalidate(readiness.Reason);
        }

        local wasReady = this.State.IsReady;
        local active = readiness.Active;

        stage = "fingerprint";
        local inputs = this._fingerprintInputs(_state, active);

        stage = "signature";
        local signature = this._sourceSignature(inputs);

        if (this.FailedReadySignature != null)
        {
            if (signature == this.FailedReadySignature)
            {
                this.State.IsReady = false;
                this.State.CurrentRaw = null;
                return null;
            }
            this.FailedReadySignature = null;
        }

        local duplicate = this.State.LastReadySignature != null
            && this.State.LastReadySignature == signature;

        if (duplicate && wasReady) return null;

        if (!duplicate)
        {
            ++this.State.SourceGeneration;
            this.State.LastReadySignature = signature;
        }

        stage = "raw_acquisition";
        local raw = this._acquireRaw(_state, active, inputs);
        raw.SourceGeneration = this.State.SourceGeneration;

        stage = "ready_commit";
        this.State.CurrentRaw = raw;
        this.State.IsReady = true;
        this.State.LastError = null;
        this.LastLoggedDiagnostic = null;
        this.State.LastEvent = {
            RecordType = "DECISION_READY",
            BattleSequence = this.State.BattleSequence,
            SourceGeneration = this.State.SourceGeneration,
            Duplicate = duplicate,
            ActiveActorID = active.getID(),
            Round = ::Tactical.TurnSequenceBar.getCurrentRound(),
            TurnPosition = ::Tactical.TurnSequenceBar.getTurnPosition()
        };

        if (!duplicate)
        {
            ::logInfo(
                "[BB-Agent Capture] READY battle=" + this.State.BattleSequence
                + " generation=" + this.State.SourceGeneration
                + " actor=" + active.getID()
            );
        }
        return this.State.LastEvent;
    }
    catch (error)
    {
        local rawError = error == null ? "null" : error.tostring();
        local loggedError = this._sanitizeDiagnosticError(rawError);
        local diagnostic = stage + "|" + loggedError;

        this.State.LastError = rawError;
        local invalidated = this.State.IsReady ? this.invalidate("capture_error") : null;

        if (diagnostic != this.LastLoggedDiagnostic)
        {
            this.LastLoggedDiagnostic = diagnostic;
            ::logError(
                "[BB-Agent Capture] capture_error stage=" + stage
                + " error=" + loggedError
                + "; advice invalidated"
            );
        }
        return invalidated;
    }
};

// Let the existing exporter retain ownership of diagnostics and invalidation.
// This wrapper only records the source signature before that existing path runs.
local originalEmitReady = liveExport._emitReady;
liveExport._emitReady = function(_event)
{
    try
    {
        return originalEmitReady.acall([this, _event]);
    }
    catch (error)
    {
        capture._latchCurrentReadyFailure();
        throw error;
    }
};
