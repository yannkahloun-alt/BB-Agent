local affordances = ::BBAGENT_Affordances;
local oracle = ::BBAGENT_DebugOracle;
local legal = ::BBAGENT_PlayerLegal;

oracle._MovementRouteScoreProjection <- null;

oracle._movementRouteScoreTrace <- function(
    _active,
    _projection,
    _tiles,
    _path,
    _route,
    _sampleIndex
)
{
    local apCosts = _active.getActionPointCosts();
    local fatigueCosts = _active.getFatigueCosts();
    local zocCounts = affordances._movementVisibleZocCounts(_projection, _tiles);
    local previous = _active.getTile();
    local totalAP = 0;
    local totalPathFatigue = 0;
    local totalZoc = 0;
    local totalScore = 0.0;

    for (local i = 0; i < _path.len(); i = ++i)
    {
        local tileId = _path[i];
        if (!(tileId in _tiles))
        {
            this._log(
                "movement_compare_route_unavailable sample=" + _sampleIndex
                + " route=" + _route
                + " tile=" + tileId
            );
            return;
        }

        local tile = _tiles[tileId];
        local step = affordances._movementStepCosts(
            _active,
            previous,
            tile,
            apCosts,
            fatigueCosts
        );
        if (step == null)
        {
            this._log(
                "movement_compare_route_untraversable sample=" + _sampleIndex
                + " route=" + _route
                + " tile=" + tileId
            );
            return;
        }

        local zoc = affordances._movementVisibleZocPenalty(zocCounts, tileId);
        local stepScore = step.ap
            + step.path_fatigue * ::Const.Movement.FatigueCostFactor
            + zoc;
        totalAP += step.ap;
        totalPathFatigue += step.path_fatigue;
        totalZoc += zoc;
        totalScore += stepScore;

        local direction = previous.getDirectionTo(tile);
        this._log(
            "movement_compare_route_step sample=" + _sampleIndex
            + " route=" + _route
            + " index=" + i
            + " from=" + legal.tileID(previous)
            + " to=" + tileId
            + " dir=" + direction
            + " terrain=" + tile.Type
            + " from_level=" + previous.Level
            + " to_level=" + tile.Level
            + " ap=" + step.ap
            + " path_fat=" + step.path_fatigue
            + " exec_fat=" + step.execution_fatigue
            + " zoc=" + zoc
            + " step_score=" + stepScore
            + " total_score=" + totalScore
        );
        previous = tile;
    }

    this._log(
        "movement_compare_route_summary sample=" + _sampleIndex
        + " route=" + _route
        + " ap=" + totalAP
        + " path_fat=" + totalPathFatigue
        + " zoc=" + totalZoc
        + " score=" + totalScore
    );
};

local originalDivergence = oracle._movementCompareDivergence;
oracle._movementCompareDivergence = function(
    _active,
    _tiles,
    _destination,
    _localPath,
    _nativePath,
    _sampleIndex
)
{
    originalDivergence.acall([
        this,
        _active,
        _tiles,
        _destination,
        _localPath,
        _nativePath,
        _sampleIndex
    ]);

    if (this._MovementRouteScoreProjection == null)
    {
        this._log(
            "movement_compare_route_score_unavailable sample=" + _sampleIndex
        );
        return;
    }

    this._movementRouteScoreTrace(
        _active,
        this._MovementRouteScoreProjection,
        _tiles,
        _localPath,
        "local",
        _sampleIndex
    );
    this._movementRouteScoreTrace(
        _active,
        this._MovementRouteScoreProjection,
        _tiles,
        _nativePath,
        "native",
        _sampleIndex
    );
};

local originalCompareOne = oracle._compareOneMovement;
oracle._compareOneMovement = function(_raw, _projection, _action, _sampleIndex)
{
    this._MovementRouteScoreProjection = _projection;
    try
    {
        local ret = originalCompareOne.acall([
            this,
            _raw,
            _projection,
            _action,
            _sampleIndex
        ]);
        this._MovementRouteScoreProjection = null;
        return ret;
    }
    catch (error)
    {
        this._MovementRouteScoreProjection = null;
        throw error;
    }
};
