local affordances = ::BBAGENT_Affordances;
local legal = ::BBAGENT_PlayerLegal;
local oracle = ::BBAGENT_DebugOracle;

// Build the Phase-A exact-visible legality set without AP/fatigue pruning. This
// stays DEBUG-only and uses the same player-legal transition generator as
// production, allowing native findPath success to be compared separately from
// resource reachability / getCostForPath completion.
oracle._movementValidationLegalTiles <- function(_raw, _projection)
{
    local active = _raw.ActiveActor;
    local origin = active.getTile();
    local originId = legal.tileID(origin);
    local tiles = affordances._movementExactVisibleTileMap(_projection);
    if (!(originId in tiles)) tiles[originId] <- origin;

    local seen = { [originId] = true };
    local queue = [originId];
    local occupancy = affordances._movementVisibleOccupancy(_projection);
    local apCosts = active.getActionPointCosts();
    local fatigueCosts = active.getFatigueCosts();

    local properties = active.getCurrentProperties();
    if (properties.IsRooted || properties.IsStunned) return seen;

    for (local cursor = 0; cursor < queue.len(); cursor = ++cursor)
    {
        local fromId = queue[cursor];
        local transitions = affordances._movementTransitionsFrom(
            active,
            _projection,
            fromId,
            tiles,
            occupancy,
            apCosts,
            fatigueCosts
        );
        foreach (transition in transitions)
        {
            local landingId = transition.landing_tile_id;
            if (landingId == null || landingId in seen) continue;
            seen[landingId] <- true;
            queue.push(landingId);
        }
    }
    return seen;
};

local originalMovementValidationPlan = oracle._movementValidationPlan;
oracle._movementValidationPlan = function(_raw, _projection)
{
    local samples = originalMovementValidationPlan.acall([this, _raw, _projection]);
    if (!this.Enabled) return samples;

    local legalTiles = this._movementValidationLegalTiles(_raw, _projection);
    local reachability = affordances._movementReachability(_raw, _projection);
    local replacementId = null;
    local legalIds = [];
    foreach (tileId, _present in legalTiles)
        if (tileId != reachability.origin_id) legalIds.push(tileId);
    legalIds.sort();
    foreach (tileId in legalIds)
    {
        if (!(tileId in reachability.nodes))
        {
            replacementId = tileId;
            break;
        }
    }

    foreach (sample in samples)
    {
        if (sample.role == "model_unreachable_visible" && replacementId != null)
        {
            sample.tile_id = replacementId;
            sample.role = "model_legal_resource_unreachable";
            sample.model_reachable = false;
            sample.model_ap = null;
            sample.model_fatigue = null;
            sample.model_execution_fatigue = null;
            sample.model_path_fatigue = null;
            sample.model_depth = null;
            sample.model_previous_tile_id = null;
        }
        sample.model_legal <- sample.tile_id in legalTiles;
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
    if (!("native_found" in sample)) return sample;
    sample.legality_agreement <- sample.model_legal == sample.native_found;
    return sample;
};

::logInfo(
    "[BB-Agent DEBUG_ORACLE] movement_validation_legality_loaded=true"
);
