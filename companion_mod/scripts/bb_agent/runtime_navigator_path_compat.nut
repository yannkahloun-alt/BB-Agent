local affordances = ::BBAGENT_Affordances;
local legal = ::BBAGENT_PlayerLegal;
local oracle = ::BBAGENT_DebugOracle;

// Pinned Battle Brothers scripts: 162f498ac7c49b4c317bbf54718a595ecef6a65a
// Battle Brothers 1.5.2.3 live smoke proved that calling the native navigator once
// for every legal destination freezes tactical play on open ground (roughly 60
// endpoints for a 9 AP actor). Production movement enumeration therefore builds
// one player-legal movement tree from visible canonical topology and owned-actor
// movement rules. DEBUG_ORACLE remains the authority for native comparison only;
// it never supplies values to this producer.
affordances._canonicalNeighbors <- function(_projection, _fromId, _toId)
{
    if (!(_fromId in _projection.runtime.tile_records)) return false;
    if (!(_toId in _projection.runtime.tile_records)) return false;
    local record = _projection.runtime.tile_records[_fromId];
    foreach (neighborId in record.neighbor_ids)
        if (neighborId == _toId) return true;
    return false;
};

affordances._movementVisibleTileMap <- function(_projection)
{
    local ret = {};
    foreach (tile in this._visibleTargetTiles(_projection))
        ret[legal.tileID(tile)] <- tile;
    return ret;
};

affordances._movementVisibleBlockedTiles <- function(_projection, _activeActorId)
{
    local blocked = {};
    foreach (actor in _projection.state.combatants)
    {
        if (actor.actor_id == _activeActorId) continue;
        if (!actor.visible || actor.life_state != "ALIVE") continue;
        if (actor.position.representation != "EXACT") continue;
        blocked[actor.position.value] <- true;
    }
    return blocked;
};

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
    local fatigue = _fatigueCosts[_toTile.Type];
    if (levelDifference != 0)
    {
        ap += _active.getLevelActionPointCost();
        fatigue += _active.getLevelFatigueCost();
        if (levelDifference > 0)
            fatigue += ::Const.Movement.LevelClimbingFatigueCost;
    }

    fatigue *= _active.getCurrentProperties().FatigueEffectMult;

    if (ap < 1 || fatigue < 0)
        throw "owned actor movement rule produced an invalid step cost";
    return { ap = ap, fatigue = fatigue };
};

affordances._movementVisibleZocPenalty <- function(_projection, _active, _tile)
{
    local reactors = this._visibleHostileReactors(_projection.state, _tile);
    return reactors.len() == 0 ? 0 : 4;
};

affordances._movementTreeIsBetter <- function(
    _score,
    _ap,
    _fatigue,
    _previous,
    _existing
)
{
    if (_existing == null) return true;
    if (_score < _existing.score) return true;
    if (_score > _existing.score) return false;
    if (_ap < _existing.ap) return true;
    if (_ap > _existing.ap) return false;
    if (_fatigue < _existing.fatigue) return true;
    if (_fatigue > _existing.fatigue) return false;
    if (_existing.previous == null) return false;
    if (_previous == null) return true;
    return _previous < _existing.previous;
};

affordances._movementTree <- function(_raw, _projection)
{
    local active = _raw.ActiveActor;
    local actorId = _projection.runtime.active_actor_id;
    local origin = active.getTile();
    local originId = legal.tileID(origin);
    local visibleTiles = this._movementVisibleTileMap(_projection);
    if (!(originId in visibleTiles))
        visibleTiles[originId] <- origin;

    local blocked = this._movementVisibleBlockedTiles(_projection, actorId);
    local apCosts = active.getActionPointCosts();
    local fatigueCosts = active.getFatigueCosts();
    if (typeof apCosts != "array" || typeof fatigueCosts != "array")
        throw "owned actor movement cost tables are unavailable";

    local apBudget = active.getActionPoints();
    local fatigueStart = active.getFatigue();
    local fatigueMax = active.getFatigueMax();
    local fatigueBudget = fatigueMax - fatigueStart;
    if (typeof apBudget != "integer" || apBudget < 0)
        throw "active actor has invalid action points";
    if (typeof fatigueStart != "integer"
        || typeof fatigueMax != "integer"
        || fatigueBudget < 0)
    {
        throw "active actor has invalid fatigue budget";
    }

    local nodes = {};
    nodes[originId] <- {
        tile = origin,
        score = 0.0,
        ap = 0,
        fatigue = 0,
        previous = null,
        closed = false
    };

    local properties = active.getCurrentProperties();
    if (properties.IsRooted || properties.IsStunned)
    {
        nodes[originId].closed = true;
        if (oracle.Enabled)
            oracle._log("movement_tree reachable=0 native_find_path_calls=0 disabled=true");
        return {
            origin_id = originId,
            tiles = visibleTiles,
            nodes = nodes
        };
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
                || (candidate.score == best.score && candidate.ap < best.ap)
                || (candidate.score == best.score && candidate.ap == best.ap
                    && candidate.fatigue < best.fatigue)
                || (candidate.score == best.score && candidate.ap == best.ap
                    && candidate.fatigue == best.fatigue && candidateId < bestId))
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
            if (neighborId == null || !(neighborId in visibleTiles)) continue;
            if (neighborId in blocked) continue;
            if (!this._canonicalNeighbors(_projection, currentId, neighborId))
                throw "movement tree encountered inconsistent canonical adjacency";

            local nextTile = visibleTiles[neighborId];
            local step = this._movementStepCosts(
                active,
                current.tile,
                nextTile,
                apCosts,
                fatigueCosts
            );
            if (step == null) continue;

            local remainingAP = apBudget - current.ap;
            local currentFatigue = fatigueStart + current.fatigue;
            if (remainingAP < step.ap
                || currentFatigue + step.fatigue > fatigueMax)
            {
                continue;
            }

            local nextRemainingAP = ::Math.round(remainingAP - step.ap);
            local nextFatigueValue = ::Math.round(currentFatigue + step.fatigue);
            local nextAP = apBudget - nextRemainingAP;
            local nextFatigue = nextFatigueValue - fatigueStart;
            if (nextAP < 0 || nextFatigue < 0
                || nextAP > apBudget || nextFatigue > fatigueBudget)
            {
                throw "owned actor movement rounding produced invalid cumulative costs";
            }

            local score = current.score
                + step.ap
                + step.fatigue * ::Const.Movement.FatigueCostFactor
                + this._movementVisibleZocPenalty(_projection, active, nextTile);

            local existing = neighborId in nodes ? nodes[neighborId] : null;
            if (!this._movementTreeIsBetter(
                score,
                nextAP,
                nextFatigue,
                currentId,
                existing
            ))
            {
                continue;
            }

            nodes[neighborId] <- {
                tile = nextTile,
                score = score,
                ap = nextAP,
                fatigue = nextFatigue,
                previous = currentId,
                closed = false
            };
            open.push(neighborId);
        }
    }

    if (oracle.Enabled)
    {
        local reachable = nodes.len() - 1;
        oracle._log(
            "movement_tree reachable=" + reachable
            + " native_find_path_calls=0"
        );
    }
    return {
        origin_id = originId,
        tiles = visibleTiles,
        nodes = nodes
    };
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

// Replace movement enumeration only. Skill, wait/end-turn, equipment, identity,
// and the hardening acquire wrapper remain unchanged.
affordances._moveActions = function(_raw, _projection)
{
    local ret = [];
    local active = _raw.ActiveActor;
    local actorId = _projection.runtime.active_actor_id;
    local tree = this._movementTree(_raw, _projection);
    local targetTiles = this._visibleTargetTiles(_projection);

    foreach (destination in targetTiles)
    {
        local destinationId = legal.tileID(destination);
        if (destinationId == tree.origin_id) continue;
        if (!(destinationId in tree.nodes)) continue;

        local node = tree.nodes[destinationId];
        local pathTiles = this._movementPathFromTree(
            tree,
            destinationId,
            _projection
        );

        local action = this._baseAction(actorId, "MOVE_TO");
        action.destination_tile_id = destinationId;
        foreach (tile in pathTiles)
            action.resolved_path.push(legal.tileID(tile));
        action.contingent_reactions = this._aooReactions(
            _projection.state,
            active,
            pathTiles
        );
        this._resolvedCosts(action, node.ap, node.fatigue);
        ret.push(action);
    }
    return ret;
};
