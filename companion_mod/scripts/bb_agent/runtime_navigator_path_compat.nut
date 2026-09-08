local affordances = ::BBAGENT_Affordances;
local legal = ::BBAGENT_PlayerLegal;
local oracle = ::BBAGENT_DebugOracle;

// Exact installed Battle Brothers 1.5.2.3 source audit, cross-checked against
// scripts revision 162f498ac7c49b4c317bbf54718a595ecef6a65a.
//
// Vanilla computeEntityPath() chooses a native path before AP/fatigue budgets are
// applied. Production therefore builds one shortest-path tree over the currently
// exact-visible player-legal subset, then applies actor.onMovementStep-equivalent
// affordability to the selected path. No native pathfinder call is made here.
// Native-only tie/ZOC semantics and discovered-fog expansion remain DEBUG_ORACLE
// validation items and never supply production values.
affordances._canonicalNeighbors <- function(_projection, _fromId, _toId)
{
    if (!(_fromId in _projection.runtime.tile_records)) return false;
    if (!(_toId in _projection.runtime.tile_records)) return false;
    local record = _projection.runtime.tile_records[_fromId];
    foreach (neighborId in record.neighbor_ids)
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

// Player cursor legality for a currently visible movement tile is based on
// Tile.IsEmpty (not merely projected living actors) and impassable terrain.
affordances._movementVisibleBlockedTiles <- function(_tiles, _originId)
{
    local blocked = {};
    foreach (tileId, tile in _tiles)
    {
        if (tileId == _originId) continue;
        if (!tile.IsEmpty) blocked[tileId] <- true;
    }
    return blocked;
};

// Return both native path-search fatigue and actor execution fatigue.
// getFatigueCosts() already applies/rounds MovementFatigueCostAdditional/Mult.
// Vanilla findPath receives that table + FatigueCostPerLevel, but not the actor,
// so FatigueEffectMult is execution-only and must not influence path scoring.
affordances._movementStepCosts <- function(
    _active,
    _fromTile,
    _toTile,
    _apCosts,
    _fatigueCosts
)
{
    if (_toTile.Type == ::Const.Tactical.TerrainType.Impassable)
        return null;
    if (_toTile.Type < 0
        || _toTile.Type >= _apCosts.len()
        || _toTile.Type >= _fatigueCosts.len())
    {
        throw "visible movement tile has unsupported terrain cost index";
    }

    local levelDifference = _toTile.Level - _fromTile.Level;
    if (::Math.abs(levelDifference) > _active.getMaxTraversibleLevels())
        return null;

    local ap = _apCosts[_toTile.Type];
    local pathFatigue = _fatigueCosts[_toTile.Type];
    if (!this._movementIsNumber(ap) || !this._movementIsNumber(pathFatigue))
        throw "owned actor movement cost table contains a non-numeric value";

    if (levelDifference != 0)
    {
        ap += _active.getLevelActionPointCost();
        pathFatigue += _active.getLevelFatigueCost();
        if (levelDifference > 0)
            pathFatigue += ::Const.Movement.LevelClimbingFatigueCost;
    }

    if (!this._movementIsNumber(ap) || ap < 1)
        throw "owned actor movement rule produced an invalid AP step cost";
    if (!this._movementIsNumber(pathFatigue) || pathFatigue < 0)
        throw "owned actor movement rule produced unsupported negative path fatigue";

    local fatigueEffectMult = _active.getCurrentProperties().FatigueEffectMult;
    if (!this._movementIsNumber(fatigueEffectMult) || fatigueEffectMult < 0)
        throw "owned actor has an unsupported fatigue effect multiplier";

    return {
        ap = ap,
        path_fatigue = pathFatigue,
        execution_fatigue = pathFatigue * fatigueEffectMult
    };
};

// Exact native ZOC edge/tie semantics are implemented in the engine, not the
// decompiled scripts. This player-legal approximation is intentionally limited
// to currently visible hostile actors; DEBUG_ORACLE samples native paths before
// this implementation can be promoted beyond the tested subset.
affordances._movementVisibleZocCounts <- function(_projection, _tiles)
{
    local counts = {};
    foreach (actor in _projection.state.combatants)
    {
        if (!actor.visible || actor.life_state != "ALIVE") continue;
        if (actor.relation != "HOSTILE") continue;
        if (actor.position.representation != "EXACT") continue;
        local actorTileId = actor.position.value;
        if (!(actorTileId in _tiles)) continue;

        local actorTile = _tiles[actorTileId];
        if (actorTile.IsEmpty) continue;
        local nativeActor = actorTile.getEntity();
        if (nativeActor == null) continue;

        local exertsZoc = false;
        try
        {
            exertsZoc = nativeActor.isExertingZoneOfControl()
                && nativeActor.hasZoneOfControl();
        }
        catch (_error)
        {
            continue;
        }
        if (!exertsZoc) continue;

        if (!(actorTileId in _projection.runtime.tile_records)) continue;
        foreach (neighborId in _projection.runtime.tile_records[actorTileId].neighbor_ids)
        {
            if (neighborId == null || !(neighborId in _tiles)) continue;
            if (!(neighborId in counts)) counts[neighborId] <- 0;
            ++counts[neighborId];
        }
    }
    return counts;
};

affordances._movementDirections <- function()
{
    return [
        ::Const.Direction.N,
        ::Const.Direction.NE,
        ::Const.Direction.SE,
        ::Const.Direction.S,
        ::Const.Direction.SW,
        ::Const.Direction.NW
    ];
};

// Resolve only reactors whose actor and position are already exact-visible in
// the player-legal state. This avoids the old hidden ZOC-count reconciliation
// and mirrors the vanilla exit-AoO guards we can prove from actor.nut.
affordances._movementVisibleAooReactors <- function(_state, _active, _originTile)
{
    local ret = [];
    if (_active.getCurrentProperties().IsImmuneToZoneOfControl) return ret;
    if (_originTile.Properties.Effect != null
        && _originTile.Properties.Effect.Type == "smoke")
    {
        return ret;
    }

    local hostileByTile = {};
    foreach (actor in _state.combatants)
    {
        if (actor.relation != "HOSTILE" || !actor.visible || actor.life_state != "ALIVE")
            continue;
        if (actor.position.representation != "EXACT") continue;
        hostileByTile[actor.position.value] <- actor.actor_id;
    }

    foreach (direction in this._movementDirections())
    {
        if (!_originTile.hasNextTile(direction)) continue;
        local tile = _originTile.getNextTile(direction);
        if (tile == null) continue;
        local tileId = legal.tileID(tile);
        if (!(tileId in hostileByTile)) continue;
        if (tile.IsEmpty) continue;

        local reactor = tile.getEntity();
        if (reactor == null) continue;
        local canReact = false;
        try
        {
            canReact = reactor.isExertingZoneOfControl()
                && reactor.hasZoneOfControl()
                && !reactor.isAlliedWith(_active);
        }
        catch (_error)
        {
            canReact = false;
        }
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
        local reactors = this._movementVisibleAooReactors(_state, _active, origin);
        foreach (actorId in reactors)
        {
            reactions.push({
                path_step_tile_id = legal.tileID(step),
                reacting_actor_id = actorId,
                reaction_kind = "AOO",
                skill_id = null,
                hit_chance = null,
                unsupported_mechanic_id = "live.player_legal.aoo_probability_unavailable"
            });
        }
        origin = step;
    }
    return reactions;
};

affordances._movementVisibleZocPenalty <- function(_zocCounts, _tileId)
{
    // Whether native ZoneOfControlCost is per occupied zone or per tile is a
    // native-engine detail. Current tested approximation applies it once per
    // tile in any visible hostile ZOC; DEBUG_ORACLE validates this choice.
    return _tileId in _zocCounts ? 4 : 0;
};

affordances._movementTreeIsBetter <- function(
    _score,
    _depth,
    _previous,
    _existing
)
{
    if (_existing == null) return true;
    if (_score < _existing.score) return true;
    if (_score > _existing.score) return false;
    if (_depth < _existing.depth) return true;
    if (_depth > _existing.depth) return false;
    if (_existing.previous == null) return false;
    if (_previous == null) return true;
    return _previous < _existing.previous;
};

// Build the path-choice tree WITHOUT AP/fatigue pruning. Vanilla findPath() is
// called before getCostForPath() receives the actor's budgets, so affordability
// cannot alter which route is selected.
affordances._movementTree <- function(_raw, _projection)
{
    local active = _raw.ActiveActor;
    local origin = active.getTile();
    local originId = legal.tileID(origin);
    local tiles = this._movementExactVisibleTileMap(_projection);
    if (!(originId in tiles)) tiles[originId] <- origin;

    local blocked = this._movementVisibleBlockedTiles(tiles, originId);
    local zocCounts = this._movementVisibleZocCounts(_projection, tiles);
    local apCosts = active.getActionPointCosts();
    local fatigueCosts = active.getFatigueCosts();
    if (typeof apCosts != "array" || typeof fatigueCosts != "array")
        throw "owned actor movement cost tables are unavailable";

    local nodes = {};
    nodes[originId] <- {
        tile = origin,
        score = 0.0,
        depth = 0,
        previous = null,
        closed = false
    };

    local properties = active.getCurrentProperties();
    if (properties.IsRooted || properties.IsStunned)
    {
        nodes[originId].closed = true;
        if (oracle.Enabled)
            oracle._log(
                "movement_tree reachable=0 native_find_path_calls=0"
                + " disabled=true scope=exact_visible discovered_scope_pending=true"
            );
        return { origin_id = originId, tiles = tiles, nodes = nodes };
    }

    local open = [originId];
    while (open.len() != 0)
    {
        local bestIndex = 0;
        for (local i = 1; i < open.len(); i = ++i)
        {
            local candidateId = open[i];
            local bestId = open[bestIndex];
            local candidate = nodes[candidateId];
            local best = nodes[bestId];
            if (candidate.score < best.score
                || (candidate.score == best.score && candidate.depth < best.depth)
                || (candidate.score == best.score && candidate.depth == best.depth
                    && candidateId < bestId))
            {
                bestIndex = i;
            }
        }

        local currentId = open[bestIndex];
        open.remove(bestIndex);
        local current = nodes[currentId];
        if (current.closed) continue;
        current.closed = true;

        if (!(currentId in _projection.runtime.tile_records))
            throw "movement tree reached a tile outside canonical records";
        local record = _projection.runtime.tile_records[currentId];

        foreach (neighborId in record.neighbor_ids)
        {
            if (neighborId == null || !(neighborId in tiles)) continue;
            if (neighborId in blocked) continue;
            if (!this._canonicalNeighbors(_projection, currentId, neighborId))
                throw "movement tree encountered inconsistent canonical adjacency";

            local nextTile = tiles[neighborId];
            local step = this._movementStepCosts(
                active,
                current.tile,
                nextTile,
                apCosts,
                fatigueCosts
            );
            if (step == null) continue;

            local score = current.score
                + step.ap
                + step.path_fatigue * ::Const.Movement.FatigueCostFactor
                + this._movementVisibleZocPenalty(zocCounts, neighborId);
            local depth = current.depth + 1;
            local existing = neighborId in nodes ? nodes[neighborId] : null;
            if (!this._movementTreeIsBetter(score, depth, currentId, existing))
                continue;

            nodes[neighborId] <- {
                tile = nextTile,
                score = score,
                depth = depth,
                previous = currentId,
                closed = false
            };
            open.push(neighborId);
        }
    }

    if (oracle.Enabled)
        oracle._log(
            "movement_tree reachable=" + (nodes.len() - 1)
            + " native_find_path_calls=0"
            + " scope=exact_visible discovered_scope_pending=true"
        );
    return { origin_id = originId, tiles = tiles, nodes = nodes };
};

affordances._movementPathFromTree <- function(_tree, _destinationId, _projection)
{
    if (!(_destinationId in _tree.nodes))
        throw "movement tree has no requested destination";
    local reversed = [];
    local cursor = _destinationId;
    local guard = 0;

    while (cursor != _tree.origin_id)
    {
        if (!(cursor in _tree.nodes))
            throw "movement tree predecessor is missing";
        local node = _tree.nodes[cursor];
        reversed.push(node.tile);
        cursor = node.previous;
        ++guard;
        if (cursor == null || guard > _tree.nodes.len())
            throw "movement tree predecessor chain is invalid";
    }

    local path = [];
    for (local i = reversed.len() - 1; i >= 0; i = --i)
        path.push(reversed[i]);

    local lastId = _tree.origin_id;
    foreach (tile in path)
    {
        local tileId = legal.tileID(tile);
        if (!this._canonicalNeighbors(_projection, lastId, tileId))
            throw "movement tree path is not canonically adjacent";
        lastId = tileId;
    }
    if (lastId != _destinationId)
        throw "movement tree path does not terminate at destination";
    return path;
};

// Mirror actor.onMovementStep() resource semantics along an already chosen path.
// The route is not changed when a step is unaffordable.
affordances._movementPathAffordability <- function(_active, _pathTiles)
{
    local apCosts = _active.getActionPointCosts();
    local fatigueCosts = _active.getFatigueCosts();
    local startAP = _active.getActionPoints();
    local startFatigue = _active.getFatigue();
    local fatigueMax = _active.getFatigueMax();
    if (!this._movementIsNumber(startAP)
        || !this._movementIsNumber(startFatigue)
        || !this._movementIsNumber(fatigueMax))
    {
        throw "owned actor movement resources are non-numeric";
    }

    local ap = startAP;
    local fatigue = startFatigue;
    local previous = _active.getTile();
    foreach (tile in _pathTiles)
    {
        local step = this._movementStepCosts(
            _active,
            previous,
            tile,
            apCosts,
            fatigueCosts
        );
        if (step == null)
            return { affordable = false, ap = 0, fatigue = 0 };
        if (ap < step.ap || fatigue + step.execution_fatigue > fatigueMax)
            return { affordable = false, ap = 0, fatigue = 0 };

        ap = ::Math.round(ap - step.ap);
        fatigue = ::Math.min(
            fatigueMax,
            ::Math.round(fatigue + step.execution_fatigue)
        );
        previous = tile;
    }

    return {
        affordable = true,
        ap = ::Math.round(startAP - ap),
        fatigue = ::Math.round(fatigue - startFatigue)
    };
};

// Replace movement enumeration only. Skill, wait/end-turn, equipment, identity,
// and the hardening acquire wrapper remain unchanged.
affordances._moveActions = function(_raw, _projection)
{
    local ret = [];
    local active = _raw.ActiveActor;
    local actorId = _projection.runtime.active_actor_id;
    local tree = this._movementTree(_raw, _projection);

    foreach (destinationId, node in tree.nodes)
    {
        if (destinationId == tree.origin_id) continue;
        local destination = node.tile;
        if (!destination.IsDiscovered) continue;
        if (!destination.IsEmpty) continue;
        if (destination.Type == ::Const.Tactical.TerrainType.Impassable) continue;

        local pathTiles = this._movementPathFromTree(tree, destinationId, _projection);
        local affordability = this._movementPathAffordability(active, pathTiles);
        if (!affordability.affordable) continue;

        local action = this._baseAction(actorId, "MOVE_TO");
        action.destination_tile_id = destinationId;
        foreach (tile in pathTiles)
            action.resolved_path.push(legal.tileID(tile));
        action.contingent_reactions = this._aooReactions(
            _projection.state,
            active,
            pathTiles
        );
        this._resolvedCosts(action, affordability.ap, affordability.fatigue);
        ret.push(action);
    }
    return ret;
};
