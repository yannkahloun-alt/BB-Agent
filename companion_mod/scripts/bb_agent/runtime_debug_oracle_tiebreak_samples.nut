local oracle = ::BBAGENT_DebugOracle;

oracle._movementTieRichContains <- function(_actions, _candidate)
{
    foreach (action in _actions)
        if (action.destination_tile_id == _candidate.destination_tile_id) return true;
    return false;
};

oracle._movementTieRichLongest <- function(_moves, _selected)
{
    local best = null;
    foreach (action in _moves)
    {
        if (action.resolved_path.len() > 4) continue;
        if (this._movementTieRichContains(_selected, action)) continue;
        if (best == null
            || action.resolved_path.len() > best.resolved_path.len()
            || (action.resolved_path.len() == best.resolved_path.len()
                && action.destination_tile_id < best.destination_tile_id))
        {
            best = action;
        }
    }
    return best;
};

// Keep one one-step sanity sample, then spend the remaining bounded native calls
// on the longest anchor-reconstructable paths where equal-cost ties are likelier.
oracle._movementCompareSamples = function(_actions)
{
    local moves = [];
    foreach (action in _actions)
        if (action.kind == "MOVE_TO") moves.push(action);
    if (moves.len() == 0) return [];

    local shortest = moves[0];
    foreach (action in moves)
    {
        if (action.resolved_path.len() < shortest.resolved_path.len()
            || (action.resolved_path.len() == shortest.resolved_path.len()
                && action.destination_tile_id < shortest.destination_tile_id))
        {
            shortest = action;
        }
    }

    local ret = [shortest];
    while (ret.len() < this.MaxMovementCompareSamples)
    {
        local next = this._movementTieRichLongest(moves, ret);
        if (next == null) break;
        ret.push(next);
    }

    this._log(
        "movement_direction_values"
        + " N=" + ::Const.Direction.N
        + " NE=" + ::Const.Direction.NE
        + " SE=" + ::Const.Direction.SE
        + " S=" + ::Const.Direction.S
        + " SW=" + ::Const.Direction.SW
        + " NW=" + ::Const.Direction.NW
    );
    return ret;
};
