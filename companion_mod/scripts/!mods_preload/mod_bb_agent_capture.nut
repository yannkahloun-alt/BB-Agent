local def = ::BBAGENT_Mod <- {
    ID = "mod_bb_agent_capture",
    Version = "0.1.0",
    Name = "BB-Agent Capture"
};

local mod = def.mh <- ::Hooks.register(def.ID, def.Version, def.Name);

mod.queue(function()
{
    ::include("bb_agent/capture_substrate");
    ::include("bb_agent/hooks/tactical_state");
});
