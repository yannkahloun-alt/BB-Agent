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
            if (::Math.abs(landingTile.Level - fromTile.Level)
                > _active.getMaxTraversibleLevels())
            {
                continue;
            }

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

// A label dominates another when it leaves at least as much AP and no more
// fatigue. Equal-resource labels may additionally discard a worse deterministic
// path score without changing reachability.
affordances._movementLabelDominates <- function(_left, _right)
{
    if (_left.ap_left < _right.ap_left) return false;
    if (_left.fatigue > _right.fatigue) return false;
    if (_left.ap_left > _right.ap_left || _left.fatigue < _right.fatigue)
        return true;
    if (_left.score < _right.score) return true;
    if (_left.score > _right.score) return false;
    if (_left.depth < _right.depth) return true;
    if (_left.depth > _right.depth) return false;
    return _left.previous_tile_id <= _right.previous_tile_id;
};

affordances._movementLabelPathPreferred <- function(_left, _right)
{
    if (_right == null) return true;
    if (_left.score < _right.score) return true;
    if (_left.score > _right.score) return false;
    if (_left.depth < _right.depth) return true;
    if (_left.depth > _right.depth) return false;
    if (_left.ap_left > _right.ap_left) return true;
    if (_left.ap_left < _right.ap_left) return false;
    if (_left.fatigue < _right.fatigue) return true;
    if (_left.fatigue > _right.fatigue) return false;
    return _left.previous_tile_id < _right.previous_tile_id;
};

affordances._movementPathFromLabel <- function(_label, _labelCount)
{
    local reversed = [];
    local cursor = _label;
    local guard = 0;
    while (cursor.previous != null)
    {
        reversed.push(cursor.tile);
        cursor = cursor.previous;
        ++guard;
        if (guard > _labelCount)
            throw "movement reachability predecessor chain is invalid";
    }

    local path = [];
    for (local i = reversed.len() - 1; i >= 0; i = --i)
        path.push(reversed[i]);
    return path;
};

// Phase B6 reachability: retain Pareto AP/fatigue labels so a destination is
// reachable whenever ANY legal player-known route is executable. Native path
// preference is intentionally not required to answer reachability.
affordances._movementReachability <- function(_raw, _projection)
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

    local startAP = active.getActionPoints();
    local startFatigue = active.getFatigue();
    local fatigueMax = active.getFatigueMax();
    if (!this._movementIsNumber(startAP)
        || !this._movementIsNumber(startFatigue)
        || !this._movementIsNumber(fatigueMax))
    {
        throw "owned actor movement resources are non-numeric";
    }

    local labels_by_tile = {};
    local originLabel = {
        tile_id = originId,
        tile = origin,
        ap_left = startAP,
        fatigue = startFatigue,
        ap_spent = 0,
        fatigue_spent = 0,
        score = 0.0,
        depth = 0,
        previous = null,
        previous_tile_id = "",
        dominated = false
    };
    labels_by_tile[originId] <- [originLabel];
    local open = [originLabel];
    local allLabels = [originLabel];
    local unresolvedJumps = [];
    local unresolvedSeen = {};

    local properties = active.getCurrentProperties();
    if (properties.IsRooted || properties.IsStunned)
    {
        if (oracle.Enabled)
            oracle._log(
                "movement_tree reachable=0 native_find_path_calls=0"
                + " disabled=true scope=exact_visible discovered_scope_pending=true"
                + " topology=issue98 resource_reachability=pareto"
            );
        return {
            origin_id = originId,
            tiles = tiles,
            nodes = { [originId] = originLabel },
            labels_by_tile = labels_by_tile,
            unresolved_jump_edges = unresolvedJumps,
            label_count = allLabels.len()
        };
    }

    while (open.len() != 0)
    {
        local bestIndex = 0;
        for (local i = 1; i < open.len(); i = ++i)
        {
            local candidate = open[i];
            local best = open[bestIndex];
            if (candidate.score < best.score
                || (candidate.score == best.score && candidate.depth < best.depth)
                || (candidate.score == best.score && candidate.depth == best.depth
                    && candidate.tile_id < best.tile_id))
            {
                bestIndex = i;
            }
        }

        local current = open[bestIndex];
        open.remove(bestIndex);
        if (current.dominated) continue;
        local currentId = current.tile_id;

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
                local jumpKey = currentId
                    + "|" + transition.via_tile_id
                    + "|" + transition.landing_tile_id;
                if (!(jumpKey in unresolvedSeen))
                {
                    unresolvedSeen[jumpKey] <- true;
                    unresolvedJumps.push({
                        from_tile_id = currentId,
                        via_tile_id = transition.via_tile_id,
                        landing_tile_id = transition.landing_tile_id
                    });
                }
                continue;
            }

            local step = transition.step;
            if (current.ap_left < step.ap) continue;
            if (current.fatigue + step.execution_fatigue > fatigueMax) continue;

            local nextAP = ::Math.round(current.ap_left - step.ap);
            local nextFatigue = ::Math.min(
                fatigueMax,
                ::Math.round(current.fatigue + step.execution_fatigue)
            );
            local neighborId = transition.landing_tile_id;
            local candidate = {
                tile_id = neighborId,
                tile = transition.landing_tile,
                ap_left = nextAP,
                fatigue = nextFatigue,
                ap_spent = ::Math.round(startAP - nextAP),
                fatigue_spent = ::Math.round(nextFatigue - startFatigue),
                score = current.score
                    + step.ap
                    + step.path_fatigue * ::Const.Movement.FatigueCostFactor
                    + this._movementZocExitPenalty(zocCounts, currentId),
                depth = current.depth + 1,
                previous = current,
                previous_tile_id = currentId,
                dominated = false
            };

            if (!(neighborId in labels_by_tile)) labels_by_tile[neighborId] <- [];
            local existingLabels = labels_by_tile[neighborId];
            local rejected = false;
            foreach (existing in existingLabels)
            {
                if (!existing.dominated
                    && this._movementLabelDominates(existing, candidate))
                {
                    rejected = true;
                    break;
                }
            }
            if (rejected) continue;

            for (local j = existingLabels.len() - 1; j >= 0; j = --j)
            {
                local existing = existingLabels[j];
                if (!existing.dominated
                    && this._movementLabelDominates(candidate, existing))
                {
                    existing.dominated = true;
                    existingLabels.remove(j);
                }
            }

            existingLabels.push(candidate);
            allLabels.push(candidate);
            open.push(candidate);
        }
    }

    local nodes = {};
    foreach (tileId, labels in labels_by_tile)
    {
        local best = null;
        foreach (label in labels)
        {
            if (label.dominated) continue;
            if (this._movementLabelPathPreferred(label, best)) best = label;
        }
        if (best != null) nodes[tileId] <- best;
    }

    if (oracle.Enabled)
        oracle._log(
            "movement_tree reachable=" + (nodes.len() - 1)
            + " native_find_path_calls=0"
            + " unresolved_jump_edges=" + unresolvedJumps.len()
            + " labels=" + allLabels.len()
            + " scope=exact_visible discovered_scope_pending=true"
            + " topology=issue98 resource_reachability=pareto"
        );
    return {
        origin_id = originId,
        tiles = tiles,
        nodes = nodes,
        labels_by_tile = labels_by_tile,
        unresolved_jump_edges = unresolvedJumps,
        label_count = allLabels.len()
    };
};

// Override final MOVE_TO enumeration so hidden raw occupancy does not leak
// through Tile.IsEmpty, and use resource-feasible labels directly rather than a
// post-hoc affordability filter on one preselected route.
affordances._moveActions = function(_raw, _projection)
{
    local ret = [];
    local active = _raw.ActiveActor;
    local actorId = _projection.runtime.active_actor_id;
    local occupancy = this._movementVisibleOccupancy(_projection);
    local tree = this._movementReachability(_raw, _projection);

    foreach (destinationId, node in tree.nodes)
    {
        if (destinationId == tree.origin_id) continue;
        local destination = node.tile;
        if (!destination.IsDiscovered) continue;
        if (destinationId in occupancy) continue;
        if (destination.Type == ::Const.Tactical.TerrainType.Impassable) continue;

        local pathTiles = this._movementPathFromLabel(node, tree.label_count);
        local action = this._baseAction(actorId, "MOVE_TO");
        action.destination_tile_id = destinationId;
        foreach (tile in pathTiles)
            action.resolved_path.push(legal.tileID(tile));
        action.contingent_reactions = this._aooReactions(
            _projection.state,
            active,
            pathTiles
        );
        this._resolvedCosts(action, node.ap_spent, node.fatigue_spent);
        ret.push(action);
    }
    return ret;
};
