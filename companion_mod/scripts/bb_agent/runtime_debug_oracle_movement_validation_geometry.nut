local affordances = ::BBAGENT_Affordances;
local legal = ::BBAGENT_PlayerLegal;
local oracle = ::BBAGENT_DebugOracle;

oracle._movementValidationModelPath <- function(_tree, _node)
{
    local nativePath = affordances._movementPathFromLabel(_node, _tree.label_count);
    local ids = [];
    foreach (tile in nativePath)
        ids.push(legal.tileID(tile));
    return ids;
};

local originalMovementValidationPlan = oracle._movementValidationPlan;
oracle._movementValidationPlan = function(_raw, _projection)
{
    local samples = originalMovementValidationPlan.acall([this, _raw, _projection]);
    if (!this.Enabled) return samples;

    local tree = affordances._movementReachability(_raw, _projection);
    foreach (sample in samples)
    {
        sample.model_path_tile_ids <- [];
        sample.model_tiles <- 0;
        sample.model_first_tile_id <- null;
        sample.model_end_tile_id <- null;
        if (!sample.model_reachable || !(sample.tile_id in tree.nodes)) continue;

        local ids = this._movementValidationModelPath(
            tree,
            tree.nodes[sample.tile_id]
        );
        sample.model_path_tile_ids = ids;
        sample.model_tiles = ids.len();
        sample.model_first_tile_id = ids.len() == 0 ? null : ids[0];
        sample.model_end_tile_id = ids.len() == 0 ? null : ids[ids.len() - 1];
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
    if (!("native_tiles" in sample)) return sample;

    sample.tile_count_agreement <- sample.model_reachable
        && sample.native_complete
        && sample.native_tiles == sample.model_tiles;
    sample.endpoint_agreement <- sample.model_reachable
        && sample.native_complete
        && sample.native_first_tile_id == sample.model_first_tile_id
        && sample.native_end_tile_id == sample.model_end_tile_id;
    return sample;
};

::logInfo(
    "[BB-Agent DEBUG_ORACLE] movement_validation_geometry_loaded=true"
);
