local def = ::BBAGENT_Mod <- {
    ID = "mod_bb_agent_capture",
    Version = "0.2.14",
    Name = "BB-Agent Capture"
};

// Smoke/debug branch opt-in. The debug-oracle implementation itself defaults
// to disabled unless this explicit root flag is true. Remove this line before
// the final production merge so normal builds remain player_legal only.
::BBAGENT_ENABLE_DEBUG_ORACLE <- true;

local mod = def.mh <- ::Hooks.register(def.ID, def.Version, def.Name);

mod.queue(function()
{
    ::include("scripts/bb_agent/capture_substrate");
    ::include("scripts/bb_agent/capture_diagnostics");
    ::include("scripts/bb_agent/affordance_source_identity");
    ::include("scripts/bb_agent/observation_memory");
    ::include("scripts/bb_agent/runtime_provenance");
    ::include("scripts/bb_agent/canonical_wire");
    ::include("scripts/bb_agent/player_legal_projection");
    ::include("scripts/bb_agent/player_legal_hardening");
    ::include("scripts/bb_agent/runtime_player_legal_actor_compat");
    ::include("scripts/bb_agent/canonical_identity");
    ::include("scripts/bb_agent/affordance_export");
    ::include("scripts/bb_agent/affordance_export_hardening");
    ::include("scripts/bb_agent/runtime_navigator_path_compat");
    ::include("scripts/bb_agent/live_export");
    ::include("scripts/bb_agent/runtime_join_compat");
    ::include("scripts/bb_agent/runtime_sha256_compat");
    ::include("scripts/bb_agent/runtime_entity_fingerprint_compat");
    ::include("scripts/bb_agent/runtime_ready_failure_latch");
    ::include("scripts/bb_agent/runtime_debug_oracle");
    ::include("scripts/bb_agent/hooks/tactical_state");
});
