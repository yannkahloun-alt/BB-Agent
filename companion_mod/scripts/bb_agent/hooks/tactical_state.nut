local mod = ::BBAGENT_Mod.mh;

mod.hook("scripts/states/tactical_state", function(q)
{
    q.onInit = @(__original) function()
    {
        __original();
        ::BBAGENT_CombatSandbox.cancel("battle_reinitialized");
        ::BBAGENT_Capture.beginBattle();
        ::BBAGENT_Capture._refreshRuntimeProvenance();
        ::BBAGENT_LiveExport.beginBattle();
    }

    q.onUpdate = @(__original) function()
    {
        __original();
        if (!::BBAGENT_Capture.isRuntimeCompatible())
        {
            ::BBAGENT_CombatSandbox.cancel("runtime_incompatible");
            if (::BBAGENT_Capture.State.IsReady && !::BBAGENT_DebugOracle.Enabled)
                ::BBAGENT_LiveExport.handleLifecycleEvent(
                    ::BBAGENT_Capture.invalidate("runtime_incompatible")
                );
            return;
        }

        local event = ::BBAGENT_Capture.observe(this);
        if (event != null && event.RecordType == "DECISION_READY")
        {
            local raw = ::BBAGENT_Capture.getCurrentRawAcquisition();
            if (raw != null) ::BBAGENT_CombatSandbox.begin(raw);
        }

        // DEBUG_ORACLE is an instrumentation mode: capture readiness still starts
        // the forensic snapshot, but normal production affordance/export work is
        // deliberately skipped so oracle collection cannot trigger large live
        // envelopes, movement probes, or logger overflow. Production is unchanged
        // when DEBUG_ORACLE is disabled.
        ::BBAGENT_CombatSandbox.pump();
        if (!::BBAGENT_DebugOracle.Enabled)
            ::BBAGENT_LiveExport.handleLifecycleEvent(event);
    }

    q.onBattleEnded = @(__original) function()
    {
        ::BBAGENT_CombatSandbox.cancel("battle_ended");
        if (::BBAGENT_Capture.State.IsReady && !::BBAGENT_DebugOracle.Enabled)
            ::BBAGENT_LiveExport.handleLifecycleEvent(
                ::BBAGENT_Capture.invalidate("battle_ended")
            );
        ::BBAGENT_Capture.endBattle("battle_ended");
        return __original();
    }

    q.onFinish = @(__original) function()
    {
        ::BBAGENT_CombatSandbox.cancel("tactical_state_finished");
        if (::BBAGENT_Capture.State.IsReady && !::BBAGENT_DebugOracle.Enabled)
            ::BBAGENT_LiveExport.handleLifecycleEvent(
                ::BBAGENT_Capture.invalidate("tactical_state_finished")
            );
        ::BBAGENT_Capture.endBattle("tactical_state_finished");
        return __original();
    }
});