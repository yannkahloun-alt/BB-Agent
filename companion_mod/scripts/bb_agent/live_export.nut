local wire = ::BBAGENT_Wire;
local capture = ::BBAGENT_Capture;
local identity = ::BBAGENT_CanonicalIdentity;

::BBAGENT_LiveExport <- {
    MaxDecodedRecordBytes = 2097152,
    MaxEncodedFrameBytes = 3145728,
    DiagnosticMaxErrorChars = 240,
    StreamStarted = false,
    LastExportStage = "idle",
    LastLoggedExportDiagnostic = null,

    function _sanitizeExportError(_error)
    {
        local errorText = _error == null ? "null" : _error.tostring();
        errorText = split(errorText, "\r\n\t").join(" ");
        if (errorText.len() > this.DiagnosticMaxErrorChars)
            errorText = errorText.slice(0, this.DiagnosticMaxErrorChars);
        return errorText;
    },

    function _reportExportFailure(_context, _error)
    {
        local errorText = this._sanitizeExportError(_error);
        local diagnostic = _context + "|" + this.LastExportStage + "|" + errorText;
        capture.State.LastError = "live export failed context=" + _context
            + " stage=" + this.LastExportStage
            + " error=" + errorText;

        if (diagnostic == this.LastLoggedExportDiagnostic) return;
        this.LastLoggedExportDiagnostic = diagnostic;
        ::logError(
            "[BB-Agent Capture] live_export_error context=" + _context
            + " stage=" + this.LastExportStage
            + " error=" + errorText
        );
    },

    function _common(_recordType)
    {
        local provenance = capture.State.Provenance;
        local mods = clone provenance.Mods;
        mods.sort();
        return {
            envelope_version = wire.EnvelopeVersion,
            capture_contract_version = wire.CaptureContractVersion,
            record_type = _recordType,
            companion_version = provenance.CompanionVersion,
            runtime_game_version = provenance.GameVersion,
            ruleset_game_version = capture.SupportedGameVersion,
            ruleset_content_fingerprint = capture.RulesetContentFingerprint,
            mods = mods,
            kernel_identity = wire.KernelIdentity
        };
    },

    function _emit(_record)
    {
        this.LastExportStage = "canonical_json";
        local raw = wire.canonicalJson(_record);
        if (raw.len() > this.MaxDecodedRecordBytes)
            throw "live record exceeds decoded payload bound";

        this.LastExportStage = "frame_encoding";
        local frame = wire.encodeFrame(_record);
        if (frame.len() > this.MaxEncodedFrameBytes)
            throw "live record exceeds encoded frame bound";

        this.LastExportStage = "log_emission";
        ::logInfo(frame);
        this.LastExportStage = "idle";
        this.LastLoggedExportDiagnostic = null;
    },

    // Called for every tactical battle, but STREAM_START belongs to the continuous
    // companion/log stream. The process-global exporter table survives across
    // battles and emits exactly one stream boundary until the mod is reloaded.
    function beginBattle()
    {
        if (this.StreamStarted) return true;
        try
        {
            this.LastExportStage = "common_envelope";
            local record = this._common("STREAM_START");
            this._emit(record);
            this.StreamStarted = true;
            return true;
        }
        catch (error)
        {
            this._reportExportFailure("STREAM_START", error);
            return false;
        }
    },

    function _requireStream()
    {
        if (!this.StreamStarted) throw "live stream has not started";
    },

    function _emitInvalidated(_event)
    {
        this.LastExportStage = "stream_required";
        this._requireStream();
        this.LastExportStage = "common_envelope";
        local record = this._common("DECISION_INVALIDATED");
        record.battle_sequence <- _event.BattleSequence;
        record.source_generation <- _event.SourceGeneration;
        record.reason <- _event.Reason;
        this._emit(record);
    },

    function _readyState(_raw)
    {
        this.LastExportStage = "player_legal_projection";
        local projection = ::BBAGENT_PlayerLegal.build(_raw);
        this.LastExportStage = "movement_sandbox_snapshot";
        ::BBAGENT_MovementSandbox.capture(_raw, projection);
        this.LastExportStage = "affordance_acquisition";
        local actions = ::BBAGENT_Affordances.acquire(_raw, projection);
        this.LastExportStage = "state_finalization";
        local state = identity.finalizeState(
            projection.state,
            actions,
            _raw.BattleSequence,
            _raw.SourceGeneration
        );

        this.LastExportStage = "capture_revalidation";
        local current = capture.getCurrentRawAcquisition();
        if (current == null
            || current.BattleSequence != _raw.BattleSequence
            || current.SourceGeneration != _raw.SourceGeneration)
        {
            throw "capture generation changed during canonical acquisition";
        }
        this.LastExportStage = "fingerprint_hash";
        local before = wire.canonicalHash(_raw.RawSourceFingerprintInputs);
        local after = wire.canonicalHash(current.RawSourceFingerprintInputs);
        if (before != after) throw "raw source changed during canonical acquisition";
        return { state = state, raw_source_fingerprint = before };
    },

    function _emitReady(_event)
    {
        this.LastExportStage = "stream_required";
        this._requireStream();
        this.LastExportStage = "raw_match";
        local raw = capture.getCurrentRawAcquisition();
        if (raw == null
            || raw.BattleSequence != _event.BattleSequence
            || raw.SourceGeneration != _event.SourceGeneration)
        {
            throw "READY lifecycle event has no matching raw acquisition";
        }
        local ready = this._readyState(raw);
        this.LastExportStage = "common_envelope";
        local record = this._common("DECISION_READY");
        record.battle_sequence <- raw.BattleSequence;
        record.source_generation <- raw.SourceGeneration;
        record.raw_source_fingerprint <- ready.raw_source_fingerprint;
        record.information_profile <- "player_legal";
        record.payload <- ready.state;
        this._emit(record);
    },

    function handleLifecycleEvent(_event)
    {
        if (_event == null) return;
        if (_event.RecordType == "DECISION_INVALIDATED")
        {
            try
            {
                this._emitInvalidated(_event);
            }
            catch (error)
            {
                this._reportExportFailure("DECISION_INVALIDATED", error);
            }
            return;
        }
        if (_event.RecordType != "DECISION_READY") return;

        try
        {
            this._emitReady(_event);
        }
        catch (error)
        {
            this._reportExportFailure("DECISION_READY", error);
            local invalidated = capture.invalidate("capture_fault");
            if (invalidated != null && invalidated.RecordType == "DECISION_INVALIDATED")
            {
                try
                {
                    this._emitInvalidated(invalidated);
                }
                catch (_emitError)
                {
                    this._reportExportFailure("CAPTURE_FAULT_INVALIDATED", _emitError);
                }
            }
        }
    }
};
