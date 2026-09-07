local affordances = ::BBAGENT_Affordances;
local legal = ::BBAGENT_PlayerLegal;
local oracle = ::BBAGENT_DebugOracle;

affordances._canonicalNeighbors <- function(_projection, _fromId, _toId)
{
    if (!(_fromId in _projection.runtime.tile_records)) return false;
    if (!(_toId in _projection.runtime.tile_records)) return false;
    foreach (neighborId in _projection.runtime.tile_records[_fromId].neighbor_ids)
        if (neighborId == _toId) return true;
    return false;
};

affordances._movementIsNumber <- function(_value)
{
    local kind = typeof _value;
    return kind == "integer" || kind == "float";
};

affordances._movementExactVisibleTileMap <- function(_projection)
{
    local ret = {};
    foreach (tile in this._visibleTargetTiles(_projection))
        ret[legal.tileID(tile)] <- tile;
    return ret;
};

affordances._movementVisibleOccupancy <- function(_projection, _tiles, _active)
{
    local ret = {};
    foreach (actor in _projection.state.combatants)
    {
        if (!actor.visible || actor.life_state != "ALIVE") continue;
        if (actor.position.representation != "EXACT") continue;
        local tileId = actor.position.value;
        if (!(tileId in _tiles)) continue;
        if (actor.actor_id == _projection.runtime.active_actor_id) continue;
        ret[tileId] <- actor.relation == "HOSTILE" ? "HOSTILE" : "ALLY";
    }
    return ret;
};

affordances._movementStepCosts <- function(_active, _fromTile, _toTile, _apCosts, _fatigueCosts)
{
    if (_toTile.Type == ::Const.Tactical.TerrainType.Impassable) return null;
    if (_toTile.Type < 0 || _toTile.Type >= _apCosts.len() || _toTile.Type >= _fatigueCosts.len())
        throw "visible movement tile has unsupported terrain cost index";

    local levelDifference = _toTile.Level - _fromTile.Level;
    if (::Math.abs(levelDifference) > _active.getMaxTraversibleLevels()) return null;

    local ap = _apCosts[_toTile.Type];
    local pathFatigue = _fatigueCosts[_toTile.Type];
    if (!this._movementIsNumber(ap) || !this._movementIsNumber(pathFatigue))
        throw "owned actor movement cost table contains a non-numeric value";
    if (levelDifference != 0)
    {
        ap += _active.getLevelActionPointCost();
        pathFatigue += _active.getLevelFatigueCost();
        if (levelDifference > 0) pathFatigue += ::Const.Movement.LevelClimbingFatigueCost;
    }
    local mult = _active.getCurrentProperties().FatigueEffectMult;
    if (!this._movementIsNumber(ap) || ap < 1 || !this._movementIsNumber(pathFatigue) || pathFatigue < 0)
        throw "owned actor movement rule produced invalid step costs";
    if (!this._movementIsNumber(mult) || mult < 0)
        throw "owned actor has an unsupported fatigue effect multiplier";
    return { ap = ap, path_fatigue = pathFatigue, execution_fatigue = pathFatigue * mult };
};

affordances._movementVisibleZocCounts <- function(_projection, _tiles)
{
    local counts = {};
    foreach (actor in _projection.state.combatants)
    {
        if (!actor.visible || actor.life_state != "ALIVE" || actor.relation != "HOSTILE") continue;
        if (actor.position.representation != "EXACT") continue;
        local actorTileId = actor.position.value;
        if (!(actorTileId in _tiles)) continue;
        local actorTile = _tiles[actorTileId];
        if (actorTile.IsEmpty) continue;
        local nativeActor = actorTile.getEntity();
        if (nativeActor == null) continue;
        local exertsZoc = false;
        try { exertsZoc = nativeActor.isExertingZoneOfControl() && nativeActor.hasZoneOfControl(); }
        catch (_error) { continue; }
        if (!exertsZoc || !(actorTileId in _projection.runtime.tile_records)) continue;
        foreach (neighborId in _projection.runtime.tile_records[actorTileId].neighbor_ids)
        {
            if (neighborId == null || !(neighborId in _tiles)) continue;
            if (!(neighborId in counts)) counts[neighborId] <- 0;
            ++counts[neighborId];
        }
    }
    return counts;
};

affordances._movementVisibleZocExitPenalty <- function(_zocCounts, _fromId)
{
    return _fromId in _zocCounts ? 4 : 0;
};

affordances._movementFriendlyJumpLanding <- function(_projection, _tiles, _occupancy, _fromId, _allyId)
{
    if (!this._canonicalNeighbors(_projection, _fromId, _allyId)) return null;
    if (!(_allyId in _projection.runtime.tile_records)) return null;
    local candidates = [];
    foreach (landingId in _projection.runtime.tile_records[_allyId].neighbor_ids)
    {
        if (landingId == null || landingId == _fromId || !(landingId in _tiles)) continue;
        if (landingId in _occupancy) continue;
        if (!_tiles[landingId].IsEmpty) continue;
        if (_tiles[landingId].Type == ::Const.Tactical.TerrainType.Impassable) continue;
        candidates.push(landingId);
    }
    candidates.sort();
    return candidates.len() == 0 ? null : candidates[0];
};

affordances._movementTransitions <- function(_projection, _tiles, _occupancy, _fromId)
{
    local ret = [];
    foreach (neighborId in _projection.runtime.tile_records[_fromId].neighbor_ids)
    {
        if (neighborId == null || !(neighborId in _tiles)) continue;
        if (!(neighborId in _occupancy)) { ret.push({ landing_id = neighborId, jumped_ally = null }); continue; }
        if (_occupancy[neighborId] != "ALLY") continue;
        local landingId = this._movementFriendlyJumpLanding(_projection, _tiles, _occupancy, _fromId, neighborId);
        if (landingId != null) ret.push({ landing_id = landingId, jumped_ally = neighborId });
    }
    ret.sort(@(a, b) a.landing_id <=> b.landing_id);
    return ret;
};

affordances._movementReachability <- function(_raw, _projection)
{
    local active = _raw.ActiveActor;
    local origin = active.getTile();
    local originId = legal.tileID(origin);
    local tiles = this._movementExactVisibleTileMap(_projection);
    if (!(originId in tiles)) tiles[originId] <- origin;
    local occupancy = this._movementVisibleOccupancy(_projection, tiles, active);
    local zocCounts = this._movementVisibleZocCounts(_projection, tiles);
    local apCosts = active.getActionPointCosts();
    local fatigueCosts = active.getFatigueCosts();
    local startAP = active.getActionPoints();
    local startFatigue = active.getFatigue();
    local fatigueMax = active.getFatigueMax();
    local nodes = {};
    nodes[originId] <- { tile = origin, ap_left = startAP, fatigue = startFatigue, ap_spent = 0, fatigue_spent = 0, score = 0.0, previous = null };

    local properties = active.getCurrentProperties();
    if (properties.IsRooted || properties.IsStunned)
        return { origin_id = originId, tiles = tiles, nodes = nodes };

    local open = [originId];
    while (open.len() != 0)
    {
        local currentId = open[0];
        open.remove(0);
        local current = nodes[currentId];
        foreach (transition in this._movementTransitions(_projection, tiles, occupancy, currentId))
        {
            local landingId = transition.landing_id;
            local landing = tiles[landingId];
            local step = this._movementStepCosts(active, current.tile, landing, apCosts, fatigueCosts);
            if (step == null) continue;
            if (current.ap_left < step.ap || current.fatigue + step.execution_fatigue > fatigueMax) continue;
            local apLeft = ::Math.round(current.ap_left - step.ap);
            local fatigue = ::Math.min(fatigueMax, ::Math.round(current.fatigue + step.execution_fatigue));
            local score = current.score + step.ap + step.path_fatigue * ::Const.Movement.FatigueCostFactor + this._movementVisibleZocExitPenalty(zocCounts, currentId);
            local candidate = { tile = landing, ap_left = apLeft, fatigue = fatigue, ap_spent = ::Math.round(startAP - apLeft), fatigue_spent = ::Math.round(fatigue - startFatigue), score = score, previous = currentId };
            local existing = landingId in nodes ? nodes[landingId] : null;
            if (existing != null && (existing.ap_left > candidate.ap_left || (existing.ap_left == candidate.ap_left && existing.fatigue <= candidate.fatigue))) continue;
            nodes[landingId] <- candidate;
            open.push(landingId);
        }
    }
    if (oracle.Enabled) oracle._log("movement_tree reachable=" + (nodes.len() - 1) + " native_find_path_calls=0 scope=exact_visible");
    return { origin_id = originId, tiles = tiles, nodes = nodes };
};

affordances._movementPathFromTree <- function(_tree, _destinationId, _projection)
{
    local reversed = [];
    local cursor = _destinationId;
    local guard = 0;
    while (cursor != _tree.origin_id)
    {
        if (!(cursor in _tree.nodes)) throw "movement tree predecessor is missing";
        local node = _tree.nodes[cursor];
        reversed.push(node.tile);
        cursor = node.previous;
        ++guard;
        if (cursor == null || guard > _tree.nodes.len()) throw "movement tree predecessor chain is invalid";
    }
    local path = [];
    for (local i = reversed.len() - 1; i >= 0; i = --i) path.push(reversed[i]);
    return path;
};

affordances._movementDirections <- function()
{
    return [::Const.Direction.N, ::Const.Direction.NE, ::Const.Direction.SE, ::Const.Direction.S, ::Const.Direction.SW, ::Const.Direction.NW];
};

affordances._movementVisibleAooReactors <- function(_state, _active, _originTile)
{
    local ret = [];
    if (_active.getCurrentProperties().IsImmuneToZoneOfControl) return ret;
    local hostileByTile = {};
    foreach (actor in _state.combatants)
        if (actor.relation == "HOSTILE" && actor.visible && actor.life_state == "ALIVE" && actor.position.representation == "EXACT") hostileByTile[actor.position.value] <- actor.actor_id;
    foreach (direction in this._movementDirections())
    {
        if (!_originTile.hasNextTile(direction)) continue;
        local tile = _originTile.getNextTile(direction);
        if (tile == null) continue;
        local tileId = legal.tileID(tile);
        if (!(tileId in hostileByTile) || tile.IsEmpty) continue;
        local reactor = tile.getEntity();
        if (reactor == null) continue;
        local canReact = false;
        try { canReact = reactor.isExertingZoneOfControl() && reactor.hasZoneOfControl() && !reactor.isAlliedWith(_active); }
        catch (_error) { canReact = false; }
        if (canReact) ret.push(hostileByTile[tileId]);
    }
    ret.sort();
    return ret;
};

affordances._aooReactions = function(_state, _active, _pathTiles)
{
    local reactions = [];
    local origin = _active.getTile();
    foreach (step in _pathTiles)
    {
        foreach (actorId in this._movementVisibleAooReactors(_state, _active, origin))
            reactions.push({ path_step_tile_id = legal.tileID(step), reacting_actor_id = actorId, reaction_kind = "AOO", skill_id = null, hit_chance = null, unsupported_mechanic_id = "live.player_legal.aoo_probability_unavailable" });
        origin = step;
    }
    return reactions;
};

affordances._moveActions = function(_raw, _projection)
{
    local ret = [];
    local active = _raw.ActiveActor;
    local actorId = _projection.runtime.active_actor_id;
    local tree = this._movementReachability(_raw, _projection);
    foreach (destinationId, node in tree.nodes)
    {
        if (destinationId == tree.origin_id) continue;
        local destination = node.tile;
        if (!destination.IsDiscovered || !destination.IsEmpty || destination.Type == ::Const.Tactical.TerrainType.Impassable) continue;
        local pathTiles = this._movementPathFromTree(tree, destinationId, _projection);
        local action = this._baseAction(actorId, "MOVE_TO");
        action.destination_tile_id = destinationId;
        foreach (tile in pathTiles) action.resolved_path.push(legal.tileID(tile));
        action.contingent_reactions = this._aooReactions(_projection.state, active, pathTiles);
        this._resolvedCosts(action, node.ap_spent, node.fatigue_spent);
        ret.push(action);
    }
    return ret;
};