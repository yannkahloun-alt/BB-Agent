local capture = ::BBAGENT_Capture;

// #70 smoke-only diagnostics: preserve fail-closed capture semantics while
// surfacing only bounded technical failure information. Never serialize or log
// tactical state, raw runtime objects, canonical payloads, or hidden truth.
capture.DiagnosticMaxErrorChars <- 240;
capture.LastLoggedDiagnostic <- null;

capture._sanitizeDiagnosticError <- function(_error)
{
    local errorText = _error == null ? "null" : _error.tostring();
    errorText = split(errorText, "\r\n\t").join(" ");
    if (errorText.len() > this.DiagnosticMaxErrorChars)
        errorText = errorText.slice(0, this.DiagnosticMaxErrorChars);
    return errorText;
};

// Preserve the original #55 capture lifecycle exactly, adding only coarse stage
// labels and deduplicated bounded error logging around the existing read-only
// helper calls.
capture.observe = function(_state)
{
    local stage = "readiness";
    try
    {
        local readiness = this._commandReadiness(_state);
        if (!readiness.Ready)
        {
            this.invalidate(readiness.Reason);
            return this.State.LastEvent;
        }

        local wasReady = this.State.IsReady;
        local active = readiness.Active;

        stage = "fingerprint";
        local inputs = this._fingerprintInputs(_state, active);

        stage = "signature";
        local signature = this._sourceSignature(inputs);
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
        this.invalidate("capture_error");

        if (diagnostic != this.LastLoggedDiagnostic)
        {
            this.LastLoggedDiagnostic = diagnostic;
            ::logError(
                "[BB-Agent Capture] capture_error stage=" + stage
                + " error=" + loggedError
                + "; advice invalidated"
            );
        }
        return this.State.LastEvent;
    }
};
