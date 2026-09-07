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
            if (::BBAGENT_Capture.State.IsReady)
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

        // Diagnostic forensic capture is deliberately pumped before normal live
        // export. One bounded record job is processed per tactical update, so a
        // later affordance/export failure cannot prevent the snapshot from making
        // progress and cannot force the whole combat dump into one game frame.
        ::BBAGENT_CombatSandbox.pump();
        ::BBAGENT_LiveExport.handleLifecycleEvent(event);
    }

    q.onBattleEnded = @(__original) function()
    {
        ::BBAGENT_CombatSandbox.cancel("battle_ended");
        if (::BBAGENT_Capture.State.IsReady)
            ::BBAGENT_LiveExport.handleLifecycleEvent(
                ::BBAGENT_Capture.invalidate("battle_ended")
            );
        ::BBAGENT_Capture.endBattle("battle_ended");
        return __original();
    }

    q.onFinish = @(__original) function()
    {
        ::BBAGENT_CombatSandbox.cancel("tactical_state_finished");
        if (::BBAGENT_Capture.State.IsReady)
            ::BBAGENT_LiveExport.handleLifecycleEvent(
                ::BBAGENT_Capture.invalidate("tactical_state_finished")
            );
        ::BBAGENT_Capture.endBattle("tactical_state_finished");
        return __original();
    }
});