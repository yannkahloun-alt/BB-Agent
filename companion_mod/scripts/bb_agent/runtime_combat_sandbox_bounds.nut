local sandbox = ::BBAGENT_CombatSandbox;

// Per-container depth/entry limits alone do not bound a branching object graph.
// Add a global node budget for each top-level reflection call, and keep any one
// logical record small enough that its chunk burst cannot monopolize a frame.
sandbox.MaxReflectNodes <- 2048;
sandbox.MaxDecodedRecordBytes = 32768;
sandbox.MaxEncodedRecordBytes = 49152;
sandbox.ReflectBudgetActive <- false;
sandbox.ReflectBudgetRemaining <- 0;

local originalReflect = sandbox._reflect;
sandbox._reflect = function(_value, _depth = 0)
{
    local root = !this.ReflectBudgetActive;
    if (root)
    {
        this.ReflectBudgetActive = true;
        this.ReflectBudgetRemaining = this.MaxReflectNodes;
    }

    if (this.ReflectBudgetRemaining <= 0)
    {
        if (root) this.ReflectBudgetActive = false;
        return {
            __bb_type = typeof _value,
            __bb_truncated = true,
            reason = "max_nodes"
        };
    }
    --this.ReflectBudgetRemaining;

    local ret = null;
    try
    {
        ret = originalReflect.acall([this, _value, _depth]);
    }
    catch (error)
    {
        if (root)
        {
            this.ReflectBudgetActive = false;
            this.ReflectBudgetRemaining = 0;
        }
        throw error;
    }

    if (root)
    {
        this.ReflectBudgetActive = false;
        this.ReflectBudgetRemaining = 0;
    }
    return ret;
};

::logInfo(
    "[BB-Agent Combat Sandbox] bounds_loaded max_nodes="
    + sandbox.MaxReflectNodes.tostring()
    + " max_record_bytes=" + sandbox.MaxDecodedRecordBytes.tostring()
);
