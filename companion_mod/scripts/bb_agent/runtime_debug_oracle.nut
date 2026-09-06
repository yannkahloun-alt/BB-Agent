local wire = ::BBAGENT_Wire;
local capture = ::BBAGENT_Capture;
local legal = ::BBAGENT_PlayerLegal;
local affordances = ::BBAGENT_Affordances;
local live = ::BBAGENT_LiveExport;

::BBAGENT_DebugOracle <- {
    ProfileVersion = "bb-agent-live-debug-oracle.v1",
    DiagnosticMaxErrorChars = 240,

    function isEnabled()
    {
        local root = getroottable();
        return ("BBAGENT_ENABLE_DEBUG_ORACLE" in root)
            && root.BBAGENT_ENABLE_DEBUG_ORACLE == true;
    },

    function _sanitizeError(_error)
    {
        local text = _error == null ? "null" : _error.tostring();
        if (text.len() > this.DiagnosticMaxErrorChars)
            text = text.slice(0, this.DiagnosticMaxErrorChars);
        return text;
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

    function _tileIDOrNull(_tile)
    {
        return _tile == null ? null : legal.tileID(_tile);
    },

    function _costInt(_costs, _primary, _fallback)
    {
        if (_primary in _costs && typeof _costs[_primary] == "integer")
            return _costs[_primary];
        if (_fallback in _costs && typeof _costs[_fallback] == "integer")
            return _costs[_fallback];
        return null;
    },

    function _costSnapshot(_costs)
    {
        local tiles = "Tiles" in _costs && typeof _costs.Tiles == "integer"
            ? _costs.Tiles
            : null;
        local complete = "IsComplete" in _costs && typeof _costs.IsComplete == "bool"
            ? _costs.IsComplete
            : null;
        local endTile = "End" in _costs ? this._tileIDOrNull(_costs.End) : null;
        return {
            tiles = tiles,
            end_tile_id = endTile,
            is_complete = complete,
            action_points_required = this._costInt(
                _costs,
                "ActionPointsRequired",
                "ActionPoints"
            ),
            fatigue_required = this._costInt(
                _costs,
                "FatigueRequired",
                "Fatigue"
            )
        };
    },

    function _mapTruth()
    {
        local ret = [];
        local native = this._nativeDirections();
        local size = ::Tactical.getMapSize();
        for (local x = 0; x < size.X; x = ++x)
        {
            for (local y = 0; y < size.Y; y = ++y)
            {
                if (!::Tactical.isValidTileSquare(x, y)) continue;
                local tile = ::Tactical.getTileSquare(x, y);
                local neighbors = array(6, null);
                for (local direction = 0; direction < 6; direction = ++direction)
                {
                    if (!tile.hasNextTile(native[direction])) continue;
                    local neighbor = tile.getNextTile(native[direction]);
                    if (neighbor != null) neighbors[direction] = legal.tileID(neighbor);
                }
                ret.push({
                    tile_id = legal.tileID(tile),
                    square_x = tile.SquareCoords.X,
                    square_y = tile.SquareCoords.Y,
                    elevation = tile.Level,
                    terrain_type = tile.Type,
                    terrain_subtype = tile.Subtype,
                    visible_for_player = tile.IsVisibleForPlayer,
                    discovered = tile.IsDiscovered,
                    empty = tile.IsEmpty,
                    native_neighbors = neighbors
                });
            }
        }
        ret.sort(@(a, b) a.tile_id <=> b.tile_id);
        return ret;
    },

    function _skillTruth(_actor)
    {
        local ret = [];
        foreach (skill in _actor.getSkills().m.Skills)
        {
            if (skill == null || skill.isGarbage()) continue;
            ret.push({
                skill_id = skill.getID(),
                active = skill.isActive(),
                hidden = skill.isHidden(),
                disabled = skill.isDisabled(),
                usable = skill.isActive() ? skill.isUsable() : false,
                affordable = skill.isActive() ? skill.isAffordable() : false
            });
        }
        ret.sort(@(a, b) a.skill_id <=> b.skill_id);
        return ret;
    },

    function _equipmentTruth(_actor)
    {
        local ret = [];
        foreach (slot, entries in _actor.getItems().m.Items)
        {
            foreach (position, item in entries)
            {
                if (item == null || item == -1 || item.isGarbage()) continue;
                local ammo = null;
                if ("getAmmo" in item)
                {
                    local currentAmmo = item.getAmmo();
                    if (typeof currentAmmo == "integer") ammo = currentAmmo;
                }
                ret.push({
                    instance_id = item.getInstanceID().tostring(),
                    content_id = item.getID(),
                    slot = slot,
                    position = position,
                    condition = item.getCondition(),
                    ammunition = ammo
                });
            }
        }
        ret.sort(@(a, b) a.instance_id <=> b.instance_id);
        return ret;
    },

    function _actorTruth(_actor)
    {
        local placed = _actor.isPlacedOnMap();
        local properties = _actor.getCurrentProperties();
        return {
            runtime_actor_id = _actor.getID().tostring(),
            player_controlled = _actor.isPlayerControlled(),
            faction = _actor.getFaction(),
            alive = _actor.isAlive(),
            placed = placed,
            hidden_to_player = placed && !_actor.isPlayerControlled()
                ? _actor.isHiddenToPlayer()
                : false,
            tile_id = placed ? legal.tileID(_actor.getTile()) : null,
            hit_points = _actor.getHitpoints(),
            maximum_hit_points = _actor.getHitpointsMax(),
            action_points = _actor.getActionPoints(),
            maximum_action_points = _actor.getActionPointsMax(),
            fatigue = _actor.getFatigue(),
            fatigue_capacity = _actor.getFatigueMax(),
            morale = _actor.getMoraleState(),
            initiative = _actor.getInitiative(),
            melee_skill = properties.getMeleeSkill(),
            ranged_skill = properties.getRangedSkill(),
            melee_defense = properties.getMeleeDefense(),
            ranged_defense = properties.getRangedDefense(),
            resolve = properties.getBravery(),
            skills = this._skillTruth(_actor),
            equipment = this._equipmentTruth(_actor)
        };
    },

    function _actorsTruth(_raw)
    {
        local ret = [];
        local groups = _raw.EntityManager.getAllInstances();
        foreach (group in groups)
        {
            foreach (actor in group)
            {
                if (actor == null) continue;
                ret.push(this._actorTruth(actor));
            }
        }
        ret.sort(@(a, b) a.runtime_actor_id <=> b.runtime_actor_id);
        return ret;
    },

    function _movementTruth(_raw)
    {
        local ret = [];
        local active = _raw.ActiveActor;
        local navigator = _raw.Navigator;
        local size = ::Tactical.getMapSize();
        local fatigueAvailable = active.getFatigueMax() - active.getFatigue();
        for (local x = 0; x < size.X; x = ++x)
        {
            for (local y = 0; y < size.Y; y = ++y)
            {
                if (!::Tactical.isValidTileSquare(x, y)) continue;
                local destination = ::Tactical.getTileSquare(x, y);
                if (!destination.IsVisibleForPlayer) continue;
                if (destination.ID == active.getTile().ID) continue;

                local entry = {
                    destination_tile_id = legal.tileID(destination),
                    found = false,
                    full = null,
                    prefixes = [],
                    error = null
                };

                navigator.clearPath();
                navigator.clearVisualisation();
                try
                {
                    local settings = affordances._movementSettings(active, navigator);
                    entry.found = navigator.findPath(active.getTile(), destination, settings, 0);
                    if (entry.found)
                    {
                        settings.ZoneOfControlCost = 0;
                        local full = navigator.getCostForPath(
                            active,
                            settings,
                            active.getActionPoints(),
                            fatigueAvailable
                        );
                        entry.full = this._costSnapshot(full);
                        local apRequired = entry.full.action_points_required;
                        if (apRequired != null && apRequired >= 0)
                        {
                            for (local budget = 0; budget <= apRequired; budget = ++budget)
                            {
                                local prefix = navigator.getCostForPath(
                                    active,
                                    settings,
                                    budget,
                                    fatigueAvailable
                                );
                                local snapshot = this._costSnapshot(prefix);
                                snapshot.ap_budget <- budget;
                                entry.prefixes.push(snapshot);
                            }
                        }
                    }
                }
                catch (error)
                {
                    entry.error = this._sanitizeError(error);
                }
                navigator.clearPath();
                navigator.clearVisualisation();
                ret.push(entry);
            }
        }
        ret.sort(@(a, b) a.destination_tile_id <=> b.destination_tile_id);
        return ret;
    },

    function build(_raw)
    {
        return {
            oracle_profile_version = this.ProfileVersion,
            battle_sequence = _raw.BattleSequence,
            source_generation = _raw.SourceGeneration,
            active_actor_runtime_id = _raw.ActiveActor.getID().tostring(),
            active_actor_tile_id = legal.tileID(_raw.ActiveActor.getTile()),
            map = this._mapTruth(),
            actors = this._actorsTruth(_raw),
            movement = this._movementTruth(_raw)
        };
    }
};

local oracle = ::BBAGENT_DebugOracle;
local originalEmitReady = live._emitReady;
live._emitReady = function(_event)
{
    if (oracle.isEnabled())
    {
        try
        {
            this.LastExportStage = "debug_oracle_raw_match";
            local raw = capture.getCurrentRawAcquisition();
            if (raw == null
                || raw.BattleSequence != _event.BattleSequence
                || raw.SourceGeneration != _event.SourceGeneration)
            {
                throw "debug oracle READY has no matching raw acquisition";
            }

            this.LastExportStage = "debug_oracle_build";
            local payload = oracle.build(raw);
            this.LastExportStage = "debug_oracle_fingerprint";
            local fingerprint = wire.canonicalHash(raw.RawSourceFingerprintInputs);
            this.LastExportStage = "debug_oracle_envelope";
            local record = this._common("DECISION_READY");
            record.battle_sequence <- raw.BattleSequence;
            record.source_generation <- raw.SourceGeneration;
            record.raw_source_fingerprint <- fingerprint;
            record.information_profile <- "omniscient_debug";
            record.payload <- payload;
            this._emit(record);
            ::logInfo(
                "[BB-Agent Oracle] READY battle=" + raw.BattleSequence
                + " generation=" + raw.SourceGeneration
                + " actor=" + raw.ActiveActor.getID()
            );
        }
        catch (error)
        {
            ::logError(
                "[BB-Agent Oracle] oracle_error stage=" + this.LastExportStage
                + " error=" + oracle._sanitizeError(error)
            );
            this.LastExportStage = "idle";
        }
    }

    return originalEmitReady.acall([this, _event]);
};
