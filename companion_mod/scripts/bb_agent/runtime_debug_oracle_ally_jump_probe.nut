local affordances = ::BBAGENT_Affordances;
local legal = ::BBAGENT_PlayerLegal;
local oracle = ::BBAGENT_DebugOracle;
local sandbox = ::BBAGENT_CombatSandbox;

oracle.LastAllyJumpProbeKey <- null;
oracle.LastAllyJumpProbeRecord <- null;

oracle._allyJumpProbeCost <- function(_costs, _preferred, _fallback)
{
    if (_costs == null) return null;
    if (_preferred in _costs) return _costs[_preferred];
    if (_fallback in _costs) return _costs[_fallback];
    return null;
};

oracle._allyJumpProbeNumber <- function(_value)
{
    return _value == null ? "null" : _value.tostring();
};

oracle._allyJumpProbeStore <- function(_raw, _record)
{
    _record.battle_sequence <- _raw.BattleSequence;
    _record.source_generation <- _raw.SourceGeneration;
    this.LastAllyJumpProbeRecord = _record;
};

oracle.probeAllyJump <- function(_raw, _projection, _tree)
{
    if (!this.Enabled) return;
    local key = _raw.BattleSequence.tostring()
        + ":"
        + _raw.SourceGeneration.tostring();
    if (this.LastAllyJumpProbeKey == key) return;
    this.LastAllyJumpProbeKey = key;
    this.LastAllyJumpProbeRecord = null;

    if (!("unresolved_jump_edges" in _tree)
        || _tree.unresolved_jump_edges.len() == 0)
    {
        this._allyJumpProbeStore(_raw, { candidate = false });
        this._log("ally_jump_probe candidate=false");
        return;
    }

    local edge = _tree.unresolved_jump_edges[0];
    if (!(edge.from_tile_id in _tree.tiles)
        || !(edge.via_tile_id in _tree.tiles)
        || !(edge.landing_tile_id in _tree.tiles))
    {
        this._allyJumpProbeStore(
            _raw,
            { candidate = false, reason = "missing_visible_tile" }
        );
        this._log("ally_jump_probe candidate=false reason=missing_visible_tile");
        return;
    }

    local active = _raw.ActiveActor;
    local origin = _tree.tiles[edge.from_tile_id];
    local ally = _tree.tiles[edge.via_tile_id];
    local landing = _tree.tiles[edge.landing_tile_id];
    local apCosts = active.getActionPointCosts();
    local fatigueCosts = active.getFatigueCosts();

    local firstStep = affordances._movementStepCosts(
        active,
        origin,
        ally,
        apCosts,
        fatigueCosts
    );
    local secondStep = affordances._movementStepCosts(
        active,
        ally,
        landing,
        apCosts,
        fatigueCosts
    );
    local landingStep = affordances._movementStepCosts(
        active,
        origin,
        landing,
        apCosts,
        fatigueCosts
    );

    local twoStepAP = firstStep != null && secondStep != null
        ? firstStep.ap + secondStep.ap
        : null;
    local twoStepFatigue = firstStep != null && secondStep != null
        ? firstStep.execution_fatigue + secondStep.execution_fatigue
        : null;
    local landingStepAP = landingStep == null ? null : landingStep.ap;
    local landingStepFatigue = landingStep == null
        ? null
        : landingStep.execution_fatigue;

    local navigator = _raw.Navigator;
    local settings = affordances._movementSettings(active, navigator);
    local found = false;
    local costs = null;

    navigator.clearPath();
    navigator.clearVisualisation();
    try
    {
        found = navigator.findPath(origin, landing, settings, 0);
        if (found)
        {
            settings.ZoneOfControlCost = 0;
            costs = navigator.getCostForPath(
                active,
                settings,
                active.getActionPoints(),
                active.getFatigueMax() - active.getFatigue()
            );
        }
    }
    catch (error)
    {
        navigator.clearPath();
        navigator.clearVisualisation();
        this._allyJumpProbeStore(
            _raw,
            {
                candidate = true,
                from_tile_id = edge.from_tile_id,
                ally_tile_id = edge.via_tile_id,
                landing_tile_id = edge.landing_tile_id,
                error = error.tostring()
            }
        );
        this._log("ally_jump_probe error=" + error.tostring());
        return;
    }
    navigator.clearPath();
    navigator.clearVisualisation();

    local nativeTiles = costs != null && "Tiles" in costs ? costs.Tiles : null;
    local nativeAP = this._allyJumpProbeCost(
        costs,
        "ActionPointsRequired",
        "ActionPoints"
    );
    local nativeFatigue = this._allyJumpProbeCost(
        costs,
        "FatigueRequired",
        "Fatigue"
    );
    local complete = costs != null && "IsComplete" in costs && costs.IsComplete;
    local first = costs != null && "First" in costs && costs.First != null
        ? legal.tileID(costs.First)
        : null;
    local end = costs != null && "End" in costs && costs.End != null
        ? legal.tileID(costs.End)
        : null;

    this._allyJumpProbeStore(
        _raw,
        {
            candidate = true,
            from_tile_id = edge.from_tile_id,
            ally_tile_id = edge.via_tile_id,
            landing_tile_id = edge.landing_tile_id,
            found = found,
            complete = complete,
            native_tiles = nativeTiles,
            native_ap = nativeAP,
            native_fatigue = nativeFatigue,
            two_step_ap = twoStepAP,
            two_step_fatigue = twoStepFatigue,
            landing_step_ap = landingStepAP,
            landing_step_fatigue = landingStepFatigue,
            first_tile_id = first,
            end_tile_id = end
        }
    );

    this._log(
        "ally_jump_probe candidate=true"
        + " from=" + edge.from_tile_id
        + " ally=" + edge.via_tile_id
        + " landing=" + edge.landing_tile_id
        + " found=" + found.tostring()
        + " complete=" + complete.tostring()
        + " native_tiles=" + this._allyJumpProbeNumber(nativeTiles)
        + " native_ap=" + this._allyJumpProbeNumber(nativeAP)
        + " native_fat=" + this._allyJumpProbeNumber(nativeFatigue)
        + " two_step_ap=" + this._allyJumpProbeNumber(twoStepAP)
        + " two_step_fat=" + this._allyJumpProbeNumber(twoStepFatigue)
        + " landing_step_ap=" + this._allyJumpProbeNumber(landingStepAP)
        + " landing_step_fat=" + this._allyJumpProbeNumber(landingStepFatigue)
        + " first=" + (first == null ? "null" : first)
        + " end=" + (end == null ? "null" : end)
    );
};

local originalMovementReachability = affordances._movementReachability;
affordances._movementReachability = function(_raw, _projection)
{
    local tree = originalMovementReachability.acall([this, _raw, _projection]);
    oracle.probeAllyJump(_raw, _projection, tree);
    return tree;
};

// DEBUG_ORACLE suppresses normal live affordance export, so explicitly run one
// bounded reachability/probe pass after the deferred player-legal projection is
// built. Append the result as an expected sandbox record before finalization.
local originalSandboxProcessJob = sandbox._processJob;
sandbox._processJob = function(_job)
{
    if (_job.kind == "ally_jump_probe_record")
    {
        this._emitRecord(this.State.raw, _job.section, _job.key, _job.target);
        return;
    }

    local wasPlayerLegalBuild = _job.kind == "player_legal_build";
    local ret = originalSandboxProcessJob.acall([this, _job]);
    if (!wasPlayerLegalBuild || this.State == null) return ret;
    if (this.State.player_legal_projection == null) return ret;

    try
    {
        affordances._movementReachability(
            this.State.raw,
            this.State.player_legal_projection
        );
    }
    catch (error)
    {
        oracle._allyJumpProbeStore(
            this.State.raw,
            { candidate = false, probe_setup_error = error.tostring() }
        );
    }

    if (oracle.LastAllyJumpProbeRecord == null)
    {
        oracle._allyJumpProbeStore(
            this.State.raw,
            { candidate = false, reason = "probe_not_produced" }
        );
    }
    this._enqueue(
        "ally_jump_probe_record",
        "debug_probe",
        "ally_jump",
        oracle.LastAllyJumpProbeRecord
    );
    return ret;
};
