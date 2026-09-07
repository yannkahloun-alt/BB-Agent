local affordances = ::BBAGENT_Affordances;
local legal = ::BBAGENT_PlayerLegal;
local oracle = ::BBAGENT_DebugOracle;

// Issue #98 Phase A/C authority: build movement topology only from the
// player-legal projection. Hidden actors are absent because only exact-visible
// projected combatants are classified here.
affordances._movementVisibleOccupancy <- function(_projection)
{
    local ret = {};
    foreach (actor in _projection.state.combatants)
    {
        if (!actor.visible || actor.life_state != "ALIVE") continue;
        if (actor.position.representation != "EXACT") continue;
        if (actor.actor_id == _projection.runtime.active_actor_id) continue;

        local kind = null;
        if (actor.relation == "HOSTILE") kind = "HOSTILE";
        else if (actor.relation == "ALLY" || actor.relation == "PLAYER") kind = "ALLY";
        else continue;

        ret[actor.position.value] <- kind;
    }
    return ret;
};

// Generate legal player-known landing transitions from one landed tile.
//
// Ordinary STEP transitions have a source-derived terrain/elevation step cost.
// ALLY_JUMP transitions deliberately carry no resolved resource cost yet: #98
// freezes the one-ally topology but leaves jump AP/fatigue charging unresolved
// until source or one bounded live observation establishes it.
affordances._movementTransitionsFrom <- function(
    _active,
    _projection,
    _fromId,
    _tiles,
    _occupancy,
    _apCosts,
    _fatigueCosts
)
{
    local ret = [];
    if (!(_fromId in _projection.runtime.tile_records)) return ret;
    if (!(_fromId in _tiles)) return ret;

    local fromTile = _tiles[_fromId];
    local record = _projection.runtime.tile_records[_fromId];

    for (
        local direction = 0;
        direction < record.neighbor_ids.len();
        direction = ++direction
    )
    {
        local neighborId = record.neighbor_ids[direction];
        if (neighborId == null || !(neighborId in _tiles)) continue;
        if (!(neighborId in _projection.runtime.tile_records)) continue;

        local occupantKind = neighborId in _occupancy ? _occupancy[neighborId] : null;
        if (occupantKind == "HOSTILE") continue;

        if (occupantKind == "ALLY")
        {
            local allyRecord = _projection.runtime.tile_records[neighborId];
            local landingId = allyRecord.neighbor_ids[direction];
            if (landingId == null || !(landingId in _tiles)) continue;
            if (!(landingId in _projection.runtime.tile_records)) continue;
            if (landingId in _occupancy) continue;

            local landingTile = _tiles[landingId];
            if (landingTile.Type == ::Const.Tactical.TerrainType.Impassable) continue;

            ret.push({
                kind = "ALLY_JUMP",
                via_tile_id = neighborId,
                landing_tile_id = landingId,
                landing_tile = landingTile,
                step = null,
                resource_cost_resolved = false
            });
            continue;
        }

        local nextTile = _tiles[neighborId];
        local step = this._movementStepCosts(
            _active,
            fromTile,
            nextTile,
            _apCosts,
            _fatigueCosts
        );
        if (step == null) continue;

        ret.push({
            kind = "STEP",
            via_tile_id = null,
            landing_tile_id = neighborId,
            landing_tile = nextTile,
            step = step,
            resource_cost_resolved = true
        });
    }

    return ret;
};

affordances._movementZocExitPenalty <- function(_zocCounts, _fromTileId)
{
    return _fromTileId in _zocCounts ? 4 : 0;
};

// Replace the direct-neighbor expansion with the #98 relation-aware transition
// layer. For now only resource-resolved ordinary STEP edges participate in the
// production path tree. Ally-jump edges are enumerated and retained as explicit
// unresolved topology until their AP/fatigue charging rule is proven.
affordances._movementTree = function(_raw, _projection)
{
    local active = _raw.ActiveActor;
    local origin = active.getTile();
    local originId = legal.tileID(origin);
    local tiles = this._movementExactVisibleTileMap(_projection);
    if (!(originId in tiles)) tiles[originId] <- origin;

    local occupancy = this._movementVisibleOccupancy(_projection);
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
    local unresolvedJumps = [];

    local properties = active.getCurrentProperties();
    if (properties.IsRooted || properties.IsStunned)
    {
        nodes[originId].closed = true;
        if (oracle.Enabled)
            oracle._log(
                "movement_tree reachable=0 native_find_path_calls=0"
                + " disabled=true scope=exact_visible discovered_scope_pending=true"
                + " topology=issue98"
            );
        return {
            origin_id = originId,
            tiles = tiles,
            nodes = nodes,
            unresolved_jump_edges = unresolvedJumps
        };
    }

    local open = [originId];
    while (open.len() != 0)
    {
        // Preserve the pre-#98 deterministic ordering for now. Exact native path
        // preference is Phase D and is not being changed in this topology cycle.
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

        local transitions = this._movementTransitionsFrom(
            active,
            _projection,
            currentId,
            tiles,
            occupancy,
            apCosts,
            fatigueCosts
        );
        foreach (transition in transitions)
        {
            if (!transition.resource_cost_resolved)
            {
                unresolvedJumps.push({
                    from_tile_id = currentId,
                    via_tile_id = transition.via_tile_id,
                    landing_tile_id = transition.landing_tile_id
                });
                continue;
            }

            local neighborId = transition.landing_tile_id;
            local step = transition.step;
            local score = current.score
                + step.ap
                + step.path_fatigue * ::Const.Movement.FatigueCostFactor
                + this._movementZocExitPenalty(zocCounts, currentId);
            local depth = current.depth + 1;
            local existing = neighborId in nodes ? nodes[neighborId] : null;
            if (!this._movementTreeIsBetter(score, depth, currentId, existing))
                continue;

            nodes[neighborId] <- {
                tile = transition.landing_tile,
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
            + " unresolved_jump_edges=" + unresolvedJumps.len()
            + " scope=exact_visible discovered_scope_pending=true"
            + " topology=issue98"
        );
    return {
        origin_id = originId,
        tiles = tiles,
        nodes = nodes,
        unresolved_jump_edges = unresolvedJumps
    };
};
