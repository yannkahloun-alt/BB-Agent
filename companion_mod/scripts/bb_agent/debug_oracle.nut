local root = getroottable();
if (!("BBAGENT_DEBUG_ORACLE" in root))
    root.BBAGENT_DEBUG_ORACLE <- false;

// Shared DEBUG_ORACLE substrate only. Concrete diagnostic probes live in their
// own bounded runtime modules so obsolete experiments cannot silently regain
// native pathfinder authority here.
::BBAGENT_DebugOracle <- {
    Enabled = root.BBAGENT_DEBUG_ORACLE == true,
    MaxLogLines = 96,
    LogLines = 0,

    function _log(_message)
    {
        if (!this.Enabled) return;
        if (this.LogLines >= this.MaxLogLines) return;
        ::logInfo("[BB-Agent Oracle] " + _message);
        ++this.LogLines;
    }
};

::logInfo(
    "[BB-Agent Oracle] substrate_loaded enabled="
    + ::BBAGENT_DebugOracle.Enabled.tostring()
    + " bounded_log_lines="
    + ::BBAGENT_DebugOracle.MaxLogLines.tostring()
);
