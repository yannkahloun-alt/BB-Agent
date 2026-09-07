local affordances = ::BBAGENT_Affordances;
local oracle = ::BBAGENT_DebugOracle;

// Native getCostForPath() fatigue semantics are intentionally not assumed here.
// Reconstruct the model's path-search fatigue independently from execution
// fatigue so bounded DEBUG_ORACLE samples can tell us which quantity BB exposes.
oracle._movementValidationPathFatigue <- function(
    _active,
    _projection,
    _tree,
    _label
)
{
    local apCosts = _active.getActionPointCosts();
    local fatigueCosts = _active.getFatigueCosts();
    local occupancy = affordances._movementVisibleOccupancy(_projection);
    local total = 0;
    local cursor = _label;
    local guard = 0;

    while (cursor != null && cursor.previous != null)
    {
        local previous = cursor.previous;
        local transitions = affordances._movementTransitionsFrom(
            _active,
            _projection,
            previous.tile_id,
            _tree.tiles,
            occupancy,
            apCosts,
            fatigueCosts
        );
        local matched = null;
        foreach (transition in transitions)
        {
            if (!transition.resource_cost_resolved) continue;
            if (transition.landing_tile_id != cursor.tile_id) continue;
            matched = transition;
            break;
        }
        if (matched == null)
            throw "movement validation could not reconstruct model transition";

        total += matched.step.path_fatigue;
        cursor = previous;
        ++guard;
        if (guard > _tree.label_count)
            throw "movement validation predecessor chain is invalid";
    }
    return total;
};

local originalMovementValidationPlan = oracle._movementValidationPlan;
oracle._movementValidationPlan = function(_raw, _projection)
{
    local samples = originalMovementValidationPlan.acall([this, _raw, _projection]);
    if (!this.Enabled) return samples;

    local tree = affordances._movementReachability(_raw, _projection);
    foreach (sample in samples)
    {
        sample.model_execution_fatigue <- sample.model_fatigue;
        sample.model_path_fatigue <- null;
        if (!sample.model_reachable) continue;
        if (!(sample.tile_id in tree.nodes)) continue;
        sample.model_path_fatigue = this._movementValidationPathFatigue(
            _raw.ActiveActor,
            _projection,
            tree,
            tree.nodes[sample.tile_id]
        );
    }
    return samples;
};

local originalMovementValidationSample = oracle._movementValidationSample;
oracle._movementValidationSample = function(_raw, _projection, _sample)
{
    local sample = originalMovementValidationSample.acall([
        this,
        _raw,
        _projection,
        _sample
    ]);
    if (!("native_fatigue" in sample)) return sample;

    sample.native_matches_execution_fatigue <- sample.model_reachable
        && sample.native_complete
        && sample.native_fatigue == sample.model_execution_fatigue;
    sample.native_matches_path_fatigue <- sample.model_reachable
        && sample.native_complete
        && sample.native_fatigue == sample.model_path_fatigue;
    return sample;
};

::logInfo(
    "[BB-Agent DEBUG_ORACLE] movement_validation_fatigue_semantics_loaded=true"
);
