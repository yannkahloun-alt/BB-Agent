local mod = ::BBAGENT_Mod.mh;

mod.hook("scripts/states/tactical_state", function(q)
{
    q.onInit = @(__original) function()
    {
        __original();
        ::BBAGENT_Capture.beginBattle();
        ::BBAGENT_Capture._refreshRuntimeProvenance();
    }

    q.onUpdate = @(__original) function()
    {
        __original();
        if (!::BBAGENT_Capture.isRuntimeCompatible())
        {
            ::BBAGENT_Capture.invalidate("runtime_incompatible");
            return;
        }
        ::BBAGENT_Capture.observe(this);
    }

    q.onBattleEnded = @(__original) function()
    {
        ::BBAGENT_Capture.endBattle("battle_ended");
        return __original();
    }

    q.onDestroy = @(__original) function()
    {
        ::BBAGENT_Capture.endBattle("tactical_state_destroyed");
        return __original();
    }
});
