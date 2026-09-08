local legal = ::BBAGENT_PlayerLegal;

// Live #102 acceptance on BB 1.5.2.3 measured the synchronous PLAYER_LEGAL
// build at 686 seconds. The projection's actor source still called
// EntityManager.getAllInstances() before the turn-list compatibility layer could
// repair the result. The tactical turn list already proved sufficient to recover
// the complete visible/owned combatant projection, so route only that one raw
// dependency through a bounded proxy while preserving the existing projection,
// hardening and memory semantics unchanged.
local originalBuild = legal.build;
legal.build = function(_raw)
{
    local current = _raw.TurnSequenceBar.getCurrentEntities();
    local raw = clone _raw;
    raw.EntityManager = {
        getAllInstances = function()
        {
            return [current];
        }
    };

    if (::BBAGENT_DebugOracle.Enabled)
        ::logInfo(
            "[BB-Agent PLAYER_LEGAL] actor_source=turn_sequence"
            + " native_entity_manager_scan=false"
            + " actors=" + current.len()
        );

    return originalBuild.acall([this, raw]);
};
