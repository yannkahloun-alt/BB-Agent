local liveExport = ::BBAGENT_LiveExport;
local oracle = ::BBAGENT_DebugOracle;

// Measure the actual production DECISION_READY export path without changing its
// behavior. DEBUG_ORACLE deliberately skips normal production export, so timing
// markers are suppressed there to avoid conflating forensic runtime with #91.
local originalEmitReady = liveExport._emitReady;
liveExport._emitReady = function(_event)
{
    if (oracle.Enabled)
        return originalEmitReady.acall([this, _event]);

    ::logInfo(
        "[BB-Agent Live Timing] ready_begin"
        + " battle=" + _event.BattleSequence.tostring()
        + " generation=" + _event.SourceGeneration.tostring()
    );
    try
    {
        local ret = originalEmitReady.acall([this, _event]);
        ::logInfo(
            "[BB-Agent Live Timing] ready_end"
            + " battle=" + _event.BattleSequence.tostring()
            + " generation=" + _event.SourceGeneration.tostring()
            + " success=true"
        );
        return ret;
    }
    catch (error)
    {
        ::logInfo(
            "[BB-Agent Live Timing] ready_end"
            + " battle=" + _event.BattleSequence.tostring()
            + " generation=" + _event.SourceGeneration.tostring()
            + " success=false"
        );
        throw error;
    }
};

::logInfo(
    "[BB-Agent Live Timing] loaded production_only=true"
    + " wraps=DECISION_READY"
);
