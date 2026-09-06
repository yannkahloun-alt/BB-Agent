::BBAGENT_DebugOracleDef <- {
    ID = "bb-agent-debug-oracle-extension",
    Version = "0.1.0",
    Name = "BB-Agent Debug Oracle"
};

// Deliberately do not register another runtime mod ID. This package is a
// development-only physical extension of mod_bb_agent_capture so the strict
// production provenance/mod-stack identity remains unchanged while it is
// installed. The package records its own oracle version in debug payloads.
if (::Hooks.hasMod("mod_bb_agent_capture"))
{
    local captureMod = ::Hooks.getMod("mod_bb_agent_capture");
    captureMod.queue(function()
    {
        ::include("scripts/bb_agent_debug_oracle/runtime_oracle");
    });
}
else
{
    ::logError("[BB-Agent Oracle] capture mod unavailable; debug oracle disabled");
}
