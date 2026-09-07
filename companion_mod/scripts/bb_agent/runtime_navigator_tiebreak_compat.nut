local affordances = ::BBAGENT_Affordances;
local legal = ::BBAGENT_PlayerLegal;
local oracle = ::BBAGENT_DebugOracle;

// Exact 1.5.2.3 smoke evidence showed an equal-cost path mismatch where native
// kept direction 3 and the prior compatibility tree replaced it with direction
// 4 solely because of invented depth/tile-id tie-breaks. Canonical neighbor_ids
// are already stored in native direction order N, NE, SE, S, SW, NW. Preserve
// first discovery on equal score so that ordering remains authoritative instead
// of imposing adapter-only lexicographic path identity.
affordances._movementTreeIsBetter = function(
    _score,
    _depth,
    _previous,
    _existing
)
{
    if (_existing == null) return true;
    return _score < _existing.score;
};

affordances._movementTree = function(_raw, _projection)
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
                + " tie_policy=native_direction_stable"
            );
        return { origin_id = originId, tiles = tiles, nodes = nodes };
    }

    local open = [originId];
    while (open.len() != 0)
    {
        // Equal scores intentionally retain array insertion order. Nodes enter
        // this array through neighbor_ids in native direction order.
        local bestIndex = 0;
        for (local i = 1; i < open.len(); i = ++i)
        {
            local candidate = nodes[open[i]];
            local best = nodes[open[bestIndex]];
            if (candidate.score < best.score)
                bestIndex = i;
        }

        local currentId = open[bestIndex];
        open.remove(bestIndex);
        local current = nodes[currentId];
        if (current.closed) continue;
        current.closed = true;

        if (!(currentId in _projection.runtime.tile_records))
            throw "movement tree reached a tile outside canonical records";
        local record = _projection.runtime.tile_records[currentId];

        for (
            local direction = 0;
            direction < record.neighbor_ids.len();
            direction = ++direction
        )
        {
            local neighborId = record.neighbor_ids[direction];
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
            + " tie_policy=native_direction_stable"
        );
    return { origin_id = originId, tiles = tiles, nodes = nodes };
};
