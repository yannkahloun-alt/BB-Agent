local def = ::BBAGENT_Mod <- {
    ID = "mod_bb_agent_capture",
    Version = "0.2.45",
    Name = "BB-Agent Capture"
};

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
    ::include("scripts/bb_agent/runtime_player_legal_numeric_compat");
    ::include("scripts/bb_agent/runtime_player_legal_blocking_compat");
    ::include("scripts/bb_agent/runtime_player_legal_actor_compat");
    ::include("scripts/bb_agent/runtime_player_legal_actor_enumeration_compat");
    ::include("scripts/bb_agent/runtime_player_legal_turn_list_fastpath");
    ::include("scripts/bb_agent/canonical_identity");
    ::include("scripts/bb_agent/affordance_export");
    ::include("scripts/bb_agent/affordance_export_hardening");
    ::include("scripts/bb_agent/debug_oracle");
    ::include("scripts/bb_agent/runtime_navigator_path_compat");
    ::include("scripts/bb_agent/runtime_movement_graph_compat");
    ::include("scripts/bb_agent/runtime_movement_ally_jump_cost_compat");
    ::include("scripts/bb_agent/runtime_movement_blocking_compat");
    ::include("scripts/bb_agent/runtime_combat_sandbox");
    ::include("scripts/bb_agent/runtime_combat_sandbox_discovery");
    ::include("scripts/bb_agent/runtime_combat_sandbox_fidelity");
    ::include("scripts/bb_agent/runtime_combat_sandbox_reference_fields");
    ::include("scripts/bb_agent/runtime_combat_sandbox_nested_fields");
    ::include("scripts/bb_agent/runtime_combat_sandbox_oracle_first");
    ::include("scripts/bb_agent/runtime_combat_sandbox_player_legal_phase");
    ::include("scripts/bb_agent/runtime_combat_sandbox_bounds");
    ::include("scripts/bb_agent/runtime_combat_sandbox_continuity");
    ::include("scripts/bb_agent/runtime_combat_sandbox_recovery");
    ::include("scripts/bb_agent/runtime_debug_oracle_ally_jump_probe");
    ::include("scripts/bb_agent/runtime_debug_oracle_ally_jump_roster_probe");
    ::include("scripts/bb_agent/runtime_debug_oracle_movement_validation");
    ::include("scripts/bb_agent/runtime_debug_oracle_movement_validation_fatigue");
    ::include("scripts/bb_agent/runtime_debug_oracle_movement_validation_legality");
    ::include("scripts/bb_agent/runtime_debug_oracle_movement_validation_geometry");
    ::include("scripts/bb_agent/runtime_debug_oracle_native_prefix_path");
    ::include("scripts/bb_agent/runtime_debug_oracle_movement_validation_remembered");
    ::include("scripts/bb_agent/live_export");
    ::include("scripts/bb_agent/runtime_join_compat");
    ::include("scripts/bb_agent/runtime_sha256_compat");
    ::include("scripts/bb_agent/runtime_entity_fingerprint_compat");
    ::include("scripts/bb_agent/runtime_ready_failure_latch");
    ::include("scripts/bb_agent/runtime_live_ready_timing");
    ::include("scripts/bb_agent/hooks/tactical_state");
});
