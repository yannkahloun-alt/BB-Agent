local mod = ::BBAGENT_Mod.mh;

mod.hook("scripts/states/tactical_state", function(q)
{
    q.onInit = @(__original) function()
    {
        __original();
        ::BBAGENT_Capture.beginBattle();
        ::BBAGENT_Capture._refreshRuntimeProvenance();
        ::BBAGENT_LiveExport.beginBattle();
    }

    q.onUpdate = @(__original) function()
    {
        __original();
        if (!::BBAGENT_Capture.isRuntimeCompatible())
        {
            if (::BBAGENT_Capture.State.IsReady)
                ::BBAGENT_LiveExport.handleLifecycleEvent(
                    ::BBAGENT_Capture.invalidate("runtime_incompatible")
                );
            return;
        }
        local event = ::BBAGENT_Capture.observe(this);
        ::BBAGENT_LiveExport.handleLifecycleEvent(event);
    }

    q.onBattleEnded = @(__original) function()
    {
        if (::BBAGENT_Capture.State.IsReady)
            ::BBAGENT_LiveExport.handleLifecycleEvent(
                ::BBAGENT_Capture.invalidate("battle_ended")
            );
        ::BBAGENT_Capture.endBattle("battle_ended");
        return __original();
    }

    q.onFinish = @(__original) function()
    {
        if (::BBAGENT_Capture.State.IsReady)
            ::BBAGENT_LiveExport.handleLifecycleEvent(
                ::BBAGENT_Capture.invalidate("tactical_state_finished")
            );
        ::BBAGENT_Capture.endBattle("tactical_state_finished");
        return __original();
    }
});
