local affordances = ::BBAGENT_Affordances;
local legal = ::BBAGENT_PlayerLegal;
local oracle = ::BBAGENT_DebugOracle;
local sandbox = ::BBAGENT_CombatSandbox;

// Phase-D diagnostic only. At most one getCostForPath() prefix query is made
// per sandbox update, and only for a capped exact-visible sample whose native
// path geometry differs from the player-legal model summary.
oracle.NativePrefixBudgetCap <- 32;

oracle._nativePrefixAnchorTiles <- function(_costs)
{
    local ret = [];
    foreach (name in ["First", "SecondLastBeforeEnd", "LastBeforeEnd", "End"])
    {
        if (!(_costs != null && name in _costs && _costs[name] != null)) continue;
        local tile = _costs[name];
        local tileId = legal.tileID(tile);
        local duplicate = false;
        foreach (existing in ret)
        {
            if (legal.tileID(existing) == tileId)
            {
                duplicate = true;
                break;
            }
        }
        if (!duplicate) ret.push(tile);
    }
    return ret;
};

oracle._insertNativePrefixJob <- function(_sandbox, _context)
{
    _sandbox.State.jobs.insert(
        _sandbox.State.cursor,
        {
            kind = "movement_validation_native_prefix",
            section = null,
            key = null,
            target = _context,
            extra = null
        }
    );
};

oracle._finishNativePrefixPath <- function(_sandbox, _context, _error = null)
{
    local sample = _context.sample;
    if (_error != null)
    {
        sample.error <- _error;
        sample.native_path_reconstruction_status <- "error";
    }
    else
    {
        sample.native_path_reconstruction_status <- "complete";
    }
    sample.native_path_tile_ids <- clone _context.path_tile_ids;
    sample.native_prefix_observations <- clone _context.observations;
    _context.navigator.clearPath();
    _context.navigator.clearVisualisation();
    _sandbox._emitRecord(
        _sandbox.State.raw,
        _context.section,
        _context.key,
        sample
    );
};

oracle._stageMovementValidationNativePath <- function(
    _sandbox,
    _job,
    _sample,
    _raw,
    _projection
)
{
    local settings = _sample._native_prefix_settings;
    delete _sample._native_prefix_settings;
    _sample.native_path_tile_ids <- [];
    _sample.native_prefix_observations <- [];

    local mismatch = _sample.model_reachable
        && _sample.native_complete
        && (("tile_count_agreement" in _sample
                && !_sample.tile_count_agreement)
            || ("endpoint_agreement" in _sample
                && !_sample.endpoint_agreement)
            || !_sample.cost_agreement);
    if (!mismatch)
    {
        _sample.native_path_reconstruction_status <- "not_requested_geometry_agrees";
        return false;
    }
    if (typeof _sample.native_ap != "integer"
        || _sample.native_ap <= 0
        || _sample.native_ap > this.NativePrefixBudgetCap)
    {
        _sample.error <- "native path AP budget is outside the bounded prefix sweep";
        _sample.native_path_reconstruction_status <- "error";
        return false;
    }

    local originId = legal.tileID(_raw.ActiveActor.getTile());
    local destinationId = _sample.tile_id;
    local context = {
        section = _job.section,
        key = _job.key,
        sample = _sample,
        navigator = _raw.Navigator,
        active = _raw.ActiveActor,
        settings = settings,
        projection = _projection,
        destination_id = destinationId,
        ap_required = _sample.native_ap,
        ap_budget = 0,
        fatigue_available = _raw.ActiveActor.getFatigueMax()
            - _raw.ActiveActor.getFatigue(),
        last_tile_id = originId,
        seen = { [originId] = true },
        path_tile_ids = [],
        observations = []
    };
    this._insertNativePrefixJob(_sandbox, context);
    return true;
};

oracle._processMovementValidationNativePrefix <- function(_sandbox, _context)
{
    local prefix = null;
    try
    {
        prefix = _context.navigator.getCostForPath(
            _context.active,
            _context.settings,
            _context.ap_budget,
            _context.fatigue_available
        );
        if (!("Tiles" in prefix)
            || typeof prefix.Tiles != "integer"
            || prefix.Tiles < 0)
        {
            throw "native movement prefix returned an invalid movement sentinel";
        }

        local observation = {
            ap_budget = _context.ap_budget,
            tiles = prefix.Tiles,
            end_tile_id = null,
            anchor_tile_ids = []
        };
        if ("End" in prefix && prefix.End != null)
            observation.end_tile_id = legal.tileID(prefix.End);

        if (prefix.Tiles != 0)
        {
            if (observation.end_tile_id == null)
                throw "native movement prefix advanced without an endpoint";
            if (observation.end_tile_id in _context.seen
                && observation.end_tile_id != _context.last_tile_id)
            {
                throw "native movement prefix revisited an earlier path endpoint";
            }
            local anchors = this._nativePrefixAnchorTiles(prefix);
            if (anchors.len() == 0)
                throw "native movement prefix exposed no path anchors";
            foreach (tile in anchors)
            {
                local tileId = legal.tileID(tile);
                observation.anchor_tile_ids.push(tileId);
                if (tileId in _context.seen) continue;
                if (!(tileId in _context.projection.runtime.tile_records))
                    throw "native movement path leaves the player-legal canonical map";
                if (!affordances._canonicalNeighbors(
                    _context.projection,
                    _context.last_tile_id,
                    tileId
                ))
                {
                    throw "native movement cost anchors left a canonical path gap";
                }
                _context.path_tile_ids.push(tileId);
                _context.seen[tileId] <- true;
                _context.last_tile_id = tileId;
            }
        }
        _context.observations.push(observation);
    }
    catch (error)
    {
        this._finishNativePrefixPath(_sandbox, _context, error.tostring());
        return;
    }

    if (_context.ap_budget >= _context.ap_required)
    {
        if (_context.path_tile_ids.len() == 0)
        {
            this._finishNativePrefixPath(
                _sandbox,
                _context,
                "native movement prefixes produced no ordered path steps"
            );
            return;
        }
        if (_context.last_tile_id != _context.destination_id)
        {
            this._finishNativePrefixPath(
                _sandbox,
                _context,
                "reconstructed native movement path does not terminate at destination"
            );
            return;
        }
        this._finishNativePrefixPath(_sandbox, _context);
        return;
    }

    ++_context.ap_budget;
    this._insertNativePrefixJob(_sandbox, _context);
};

local originalSandboxProcessJob = sandbox._processJob;
sandbox._processJob = function(_job)
{
    if (_job.kind == "movement_validation_native_prefix")
    {
        if (!oracle.Enabled)
        {
            oracle._finishNativePrefixPath(
                this,
                _job.target,
                "debug_oracle_disabled"
            );
            return;
        }
        oracle._processMovementValidationNativePrefix(this, _job.target);
        return;
    }
    return originalSandboxProcessJob.acall([this, _job]);
};

::logInfo(
    "[BB-Agent DEBUG_ORACLE] native_prefix_path_loaded=true"
    + " one_prefix_query_per_update=true ap_budget_cap="
    + oracle.NativePrefixBudgetCap.tostring()
);
