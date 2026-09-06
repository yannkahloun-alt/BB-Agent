local capture = ::BBAGENT_Capture;

// Expose a detached view of legal observation-memory entries. The projected
// Value remains owned by #57, but callers cannot mutate the capture store's
// keys or observation metadata through the returned table.
capture.getObservationMemory = function()
{
    local snapshot = {};
    foreach (key, fact in this.State.ObservationMemory)
    {
        snapshot[key] <- {
            Value = fact.Value,
            ObservedRound = fact.ObservedRound,
            ObservedDecision = fact.ObservedDecision
        };
    }
    return snapshot;
};
