local affordances = ::BBAGENT_Affordances;
local legal = ::BBAGENT_PlayerLegal;
local oracle = ::BBAGENT_DebugOracle;

oracle.LastAllyJumpProbeKey <- null;

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

oracle.probeAllyJump <- function(_raw, _projection, _tree)
{
    if (!this.Enabled) return;
    local key = _raw.BattleSequence + ":" + _raw.SourceGeneration;
    if (this.LastAllyJumpProbeKey == key) return;
    this.LastAllyJumpProbeKey = key;

    if (!("unresolved_jump_edges" in _tree)
        || _tree.unresolved_jump_edges.len() == 0)
    {
        this._log("ally_jump_probe candidate=false");
        return;
    }

    local edge = _tree.unresolved_jump_edges[0];
    if (!(edge.from_tile_id in _tree.tiles)
        || !(edge.via_tile_id in _tree.tiles)
        || !(edge.landing_tile_id in _tree.tiles))
    {
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
        this._log("ally_jump_probe error=" + error);
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
        : "null";
    local end = costs != null && "End" in costs && costs.End != null
        ? legal.tileID(costs.End)
        : "null";

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
        + " first=" + first
        + " end=" + end
    );
};

local originalMovementTree = affordances._movementTree;
affordances._movementTree = function(_raw, _projection)
{
    local tree = originalMovementTree.acall([this, _raw, _projection]);
    oracle.probeAllyJump(_raw, _projection, tree);
    return tree;
};
