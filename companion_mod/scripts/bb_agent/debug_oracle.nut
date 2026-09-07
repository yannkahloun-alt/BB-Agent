local root = getroottable();
if (!("BBAGENT_DEBUG_ORACLE" in root))
    root.BBAGENT_DEBUG_ORACLE <- false;

local legal = ::BBAGENT_PlayerLegal;

::BBAGENT_DebugOracle <- {
    Enabled = root.BBAGENT_DEBUG_ORACLE == true,
    MaxLogLines = 96,
    MaxBudget = 32,
    MaxPathEntries = 24,
    MovementMismatchCaptured = false,
    LogLines = 0,
    NavigatorPathSlots = 0,

    function _log(_message)
    {
        if (!this.Enabled) return;
        if (this.LogLines >= this.MaxLogLines) return;
        ::logInfo("[BB-Agent Oracle] " + _message);
        ++this.LogLines;
    },

    function _costValue(_costs, _preferred, _fallback)
    {
        if (_preferred in _costs) return _costs[_preferred].tostring();
        if (_fallback in _costs) return _costs[_fallback].tostring();
        return "missing";
    },

    function _costSummary(_costs)
    {
        if (_costs == null) return "null";
        local tiles = "missing";
        local endId = "null";
        local complete = "missing";
        if ("Tiles" in _costs) tiles = _costs.Tiles.tostring();
        if ("End" in _costs && _costs.End != null) endId = legal.tileID(_costs.End);
        if ("IsComplete" in _costs) complete = _costs.IsComplete.tostring();
        return "tiles=" + tiles
            + " end=" + endId
            + " complete=" + complete
            + " ap=" + this._costValue(_costs, "ActionPointsRequired", "ActionPoints")
            + " fat=" + this._costValue(_costs, "FatigueRequired", "Fatigue");
    },

    function _nativeTile(_tile)
    {
        if (_tile == null) return "null";
        local runtimeId = "unavailable";
        local square = "unavailable";
        local canonicalId = "unavailable";
        try
        {
            runtimeId = _tile.ID.tostring();
        }
        catch (_error)
        {
        }
        try
        {
            square = _tile.SquareCoords.X + ":" + _tile.SquareCoords.Y;
            canonicalId = legal.tileID(_tile);
        }
        catch (_error)
        {
        }
        return canonicalId + " native_id=" + runtimeId + " square=" + square;
    },

    function _canonicalNeighbors(_record)
    {
        if (_record == null) return "missing";
        local ret = "[";
        for (local i = 0; i < _record.neighbor_ids.len(); i = ++i)
        {
            if (i != 0) ret += ",";
            local neighbor = _record.neighbor_ids[i];
            ret += (neighbor == null ? "null" : neighbor);
        }
        return ret + "]";
    },

    function _canonicalCoordinate(_record)
    {
        if (_record == null || !("coordinate" in _record) || _record.coordinate == null)
            return "missing";
        return "q=" + _record.coordinate.q + ",r=" + _record.coordinate.r;
    },

    function _isCanonicalNeighbor(_projection, _fromId, _toId)
    {
        if (!(_fromId in _projection.runtime.tile_records)) return false;
        if (!(_toId in _projection.runtime.tile_records)) return false;
        local record = _projection.runtime.tile_records[_fromId];
        foreach (neighborId in record.neighbor_ids)
            if (neighborId == _toId) return true;
        return false;
    },

    function _nativeDirections()
    {
        return [
            ::Const.Direction.N,
            ::Const.Direction.NE,
            ::Const.Direction.SE,
            ::Const.Direction.S,
            ::Const.Direction.SW,
            ::Const.Direction.NW
        ];
    },

    function _dumpNativeNeighbors(_tile)
    {
        local directions = this._nativeDirections();
        for (local i = 0; i < directions.len(); i = ++i)
        {
            local direction = directions[i];
            local hasNeighbor = false;
            local neighbor = null;
            try
            {
                hasNeighbor = _tile.hasNextTile(direction);
                if (hasNeighbor) neighbor = _tile.getNextTile(direction);
            }
            catch (error)
            {
                this._log("native_neighbor direction=" + i + " error=" + error.tostring());
                continue;
            }
            this._log(
                "native_neighbor direction=" + i
                + " present=" + hasNeighbor.tostring()
                + " tile=" + (neighbor == null ? "null" : this._nativeTile(neighbor))
            );
        }
    },

    function _dumpTwoStepBridges(_from, _to)
    {
        local directions = this._nativeDirections();
        local targetId = legal.tileID(_to);
        local bridgeCount = 0;
        for (local i = 0; i < directions.len(); i = ++i)
        {
            local middle = null;
            try
            {
                if (!_from.hasNextTile(directions[i])) continue;
                middle = _from.getNextTile(directions[i]);
            }
            catch (_error)
            {
                continue;
            }
            if (middle == null) continue;

            for (local j = 0; j < directions.len(); j = ++j)
            {
                local candidate = null;
                try
                {
                    if (!middle.hasNextTile(directions[j])) continue;
                    candidate = middle.getNextTile(directions[j]);
                }
                catch (_error)
                {
                    continue;
                }
                if (candidate == null) continue;
                if (legal.tileID(candidate) != targetId) continue;
                ++bridgeCount;
                this._log(
                    "native_two_step_bridge index=" + bridgeCount
                    + " middle=" + this._nativeTile(middle)
                    + " from_direction=" + i
                    + " to_direction=" + j
                );
            }
        }
        this._log("native_two_step_bridge_count=" + bridgeCount);
    },

    function _describePathEntry(_entry)
    {
        if (_entry == null) return "null";
        local kind = typeof _entry;
        if (kind == "bool" || kind == "integer" || kind == "float" || kind == "string")
            return kind + ":" + _entry.tostring();
        if (kind != "table" && kind != "instance")
            return kind;

        try
        {
            local square = _entry.SquareCoords;
            if (square != null) return "tile:" + this._nativeTile(_entry);
        }
        catch (_error)
        {
        }

        try
        {
            if (_entry.Tile != null) return "Tile=" + this._nativeTile(_entry.Tile);
        }
        catch (_error)
        {
        }
        try
        {
            if (_entry.tile != null) return "tile=" + this._nativeTile(_entry.tile);
        }
        catch (_error)
        {
        }
        try
        {
            if (_entry.End != null) return "End=" + this._nativeTile(_entry.End);
        }
        catch (_error)
        {
        }
        try
        {
            if (_entry.end != null) return "end=" + this._nativeTile(_entry.end);
        }
        catch (_error)
        {
        }
        return kind;
    },

    function _dumpPathValue(_name, _value)
    {
        ++this.NavigatorPathSlots;
        local kind = typeof _value;
        this._log("navigator_path_slot name=" + _name + " type=" + kind);
        if (kind == "array")
        {
            local limit = ::Math.min(_value.len(), this.MaxPathEntries);
            this._log("navigator_path_array name=" + _name + " length=" + _value.len());
            for (local i = 0; i < limit; i = ++i)
                this._log(
                    "navigator_path_entry name=" + _name
                    + " index=" + i
                    + " value=" + this._describePathEntry(_value[i])
                );
            if (_value.len() > limit)
                this._log("navigator_path_array name=" + _name + " truncated=true");
            return;
        }

        if (kind != "table" && kind != "instance") return;
        try
        {
            local count = 0;
            foreach (key, value in _value)
            {
                if (count >= this.MaxPathEntries)
                {
                    this._log("navigator_path_object name=" + _name + " truncated=true");
                    break;
                }
                this._log(
                    "navigator_path_object name=" + _name
                    + " key=" + key.tostring()
                    + " type=" + typeof value
                    + " value=" + this._describePathEntry(value)
                );
                ++count;
            }
        }
        catch (error)
        {
            this._log(
                "navigator_path_object name=" + _name
                + " iterate_error=" + error.tostring()
            );
        }
    },

    function _dumpCostFields(_label, _costs)
    {
        if (_costs == null) return;
        try
        {
            foreach (key, value in _costs)
            {
                local name = key.tostring();
                this._log(
                    "cost_field label=" + _label
                    + " key=" + name
                    + " type=" + typeof value
                );
                if (name.find("Path") != null
                    || name.find("path") != null
                    || name.find("Node") != null
                    || name.find("node") != null
                    || name.find("Step") != null
                    || name.find("step") != null)
                {
                    this._dumpPathValue("cost." + _label + "." + name, value);
                }
            }
        }
        catch (error)
        {
            this._log("cost_field_scan label=" + _label + " error=" + error.tostring());
        }
    },

    function _probeNavigatorInternals(_navigator)
    {
        this.NavigatorPathSlots = 0;

        try
        {
            this._dumpPathValue("navigator.getPath()", _navigator.getPath());
        }
        catch (error)
        {
            this._log("navigator_probe name=getPath error=" + error.tostring());
        }

        try
        {
            this._dumpPathValue("navigator.Path", _navigator.Path);
        }
        catch (error)
        {
            this._log("navigator_probe name=Path error=" + error.tostring());
        }

        try
        {
            this._dumpPathValue("navigator.m.Path", _navigator.m.Path);
        }
        catch (error)
        {
            this._log("navigator_probe name=m.Path error=" + error.tostring());
        }

        try
        {
            this._dumpPathValue("navigator.m.PathTiles", _navigator.m.PathTiles);
        }
        catch (error)
        {
            this._log("navigator_probe name=m.PathTiles error=" + error.tostring());
        }

        try
        {
            this._dumpPathValue("navigator.m.CurrentPath", _navigator.m.CurrentPath);
        }
        catch (error)
        {
            this._log("navigator_probe name=m.CurrentPath error=" + error.tostring());
        }

        try
        {
            this._dumpPathValue("navigator.m.PathResult", _navigator.m.PathResult);
        }
        catch (error)
        {
            this._log("navigator_probe name=m.PathResult error=" + error.tostring());
        }

        try
        {
            this._dumpPathValue("navigator.m.Nodes", _navigator.m.Nodes);
        }
        catch (error)
        {
            this._log("navigator_probe name=m.Nodes error=" + error.tostring());
        }

        try
        {
            this._dumpPathValue("navigator.getCurrentPath()", _navigator.getCurrentPath());
        }
        catch (error)
        {
            this._log("navigator_probe name=getCurrentPath error=" + error.tostring());
        }

        try
        {
            this._dumpPathValue("navigator.getPathTiles()", _navigator.getPathTiles());
        }
        catch (error)
        {
            this._log("navigator_probe name=getPathTiles error=" + error.tostring());
        }

        try
        {
            this._dumpPathValue("navigator.getPathNodes()", _navigator.getPathNodes());
        }
        catch (error)
        {
            this._log("navigator_probe name=getPathNodes error=" + error.tostring());
        }

        this._log("navigator_path_slots_found=" + this.NavigatorPathSlots);
    },

    function reportMovementTopologyMismatch(
        _navigator,
        _active,
        _settings,
        _costs,
        _destination,
        _projection,
        _previous,
        _next
    )
    {
        if (!this.Enabled || this.MovementMismatchCaptured) return;
        this.MovementMismatchCaptured = true;
        this.LogLines = 0;

        local origin = _active.getTile();
        local previousId = legal.tileID(_previous);
        local nextId = legal.tileID(_next);
        local destinationId = legal.tileID(_destination);

        this._log("mode=DEBUG_ORACLE event=movement_topology_mismatch");
        this._log(
            "origin=" + this._nativeTile(origin)
            + " destination=" + this._nativeTile(_destination)
        );
        this._log("full_native " + this._costSummary(_costs));
        this._dumpCostFields("full", _costs);

        local apRequired = 0;
        if ("ActionPointsRequired" in _costs) apRequired = _costs.ActionPointsRequired;
        else if ("ActionPoints" in _costs) apRequired = _costs.ActionPoints;
        local budgetLimit = ::Math.min(apRequired, this.MaxBudget);
        local fatigueAvailable = _active.getFatigueMax() - _active.getFatigue();
        for (local budget = 0; budget <= budgetLimit; budget = ++budget)
        {
            try
            {
                local prefix = _navigator.getCostForPath(
                    _active,
                    _settings,
                    budget,
                    fatigueAvailable
                );
                this._log("budget=" + budget + " " + this._costSummary(prefix));
                if (budget == 0 || budget == budgetLimit)
                    this._dumpCostFields("budget_" + budget, prefix);
            }
            catch (error)
            {
                this._log("budget=" + budget + " error=" + error.tostring());
            }
        }
        if (apRequired > budgetLimit)
            this._log("budget_trace truncated=true ap_required=" + apRequired);

        this._log(
            "transition previous=" + this._nativeTile(_previous)
            + " next=" + this._nativeTile(_next)
        );
        this._dumpNativeNeighbors(_previous);
        this._dumpTwoStepBridges(_previous, _next);

        local previousRecord = previousId in _projection.runtime.tile_records
            ? _projection.runtime.tile_records[previousId]
            : null;
        local nextRecord = nextId in _projection.runtime.tile_records
            ? _projection.runtime.tile_records[nextId]
            : null;
        this._log(
            "canonical_previous id=" + previousId
            + " in_projection=" + (previousRecord != null ? "true" : "false")
            + " coordinate=" + this._canonicalCoordinate(previousRecord)
            + " neighbors=" + this._canonicalNeighbors(previousRecord)
        );
        this._log(
            "canonical_next id=" + nextId
            + " in_projection=" + (nextRecord != null ? "true" : "false")
            + " coordinate=" + this._canonicalCoordinate(nextRecord)
        );
        local canonicalNeighbor = this._isCanonicalNeighbor(
            _projection,
            previousId,
            nextId
        );
        this._log(
            "canonical_neighbor=" + canonicalNeighbor.tostring()
            + " destination_id=" + destinationId
        );

        this._probeNavigatorInternals(_navigator);
        this._log("event=movement_topology_mismatch end=true");
    }
};
