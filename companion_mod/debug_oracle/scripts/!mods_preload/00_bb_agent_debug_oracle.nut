local root = getroottable();
if ("BBAGENT_DEBUG_ORACLE" in root)
    root.BBAGENT_DEBUG_ORACLE = true;
else
    root.BBAGENT_DEBUG_ORACLE <- true;

::logInfo("[BB-Agent Oracle] DEBUG_ORACLE explicitly enabled by development overlay");
