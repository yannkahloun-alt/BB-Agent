local wire = ::BBAGENT_Wire;
local capture = ::BBAGENT_Capture;

::BBAGENT_PlayerLegal <- {
    State = {
        BattleSequence = -1,
        NextItemID = 0,
        ItemIDs = {}
    },

    function _ensureBattle(_raw)
    {
        if (this.State.BattleSequence == _raw.BattleSequence) return;
        this.State.BattleSequence = _raw.BattleSequence;
        this.State.NextItemID = 0;
        this.State.ItemIDs = {};
    },

    function actorID(_actor)
    {
        return "actor:" + _actor.getID();
    },

    function tileID(_tile)
    {
        return "tile:" + _tile.SquareCoords.X + ":" + _tile.SquareCoords.Y;
    },

    function _slotName(_slot)
    {
        if (_slot == ::Const.ItemSlot.Mainhand) return "mainhand";
        if (_slot == ::Const.ItemSlot.Offhand) return "offhand";
        if (_slot == ::Const.ItemSlot.Head) return "head";
        if (_slot == ::Const.ItemSlot.Body) return "body";
        if (_slot == ::Const.ItemSlot.Ammo) return "ammo";
        if (_slot == ::Const.ItemSlot.Accessory) return "accessory";
        if (_slot == ::Const.ItemSlot.Bag) return "bag";
        return "slot:" + _slot;
    },

    function slotLocation(_slot, _position)
    {
        local name = this._slotName(_slot);
        return _slot == ::Const.ItemSlot.Bag ? name + ":" + _position : name;
    },

    function itemID(_actor, _item)
    {
        local runtime = _item.getInstanceID();
        if (!(runtime in this.State.ItemIDs))
        {
            local id = "item:" + this.State.BattleSequence + ":" + this.State.NextItemID;
            ++this.State.NextItemID;
            this.State.ItemIDs[runtime] <- id;
        }
        return this.State.ItemIDs[runtime];
    },

    function _unknownResources()
    {
        return {
            hit_points = wire.unknownValue(),
            maximum_hit_points = wire.unknownValue(),
            action_points = wire.unknownValue(),
            maximum_action_points = wire.unknownValue(),
            fatigue = wire.unknownValue(),
            fatigue_capacity = wire.unknownValue(),
            head_armor = wire.unknownValue(),
            maximum_head_armor = wire.unknownValue(),
            body_armor = wire.unknownValue(),
            maximum_body_armor = wire.unknownValue(),
            morale = wire.unknownValue(),
            initiative = wire.unknownValue()
        };
    },

    function _ownedResources(_actor)
    {
        return {
            hit_points = wire.exactObserved(_actor.getHitpoints()),
            maximum_hit_points = wire.exactObserved(_actor.getHitpointsMax()),
            action_points = wire.exactObserved(_actor.getActionPoints()),
            maximum_action_points = wire.exactObserved(_actor.getActionPointsMax()),
            fatigue = wire.exactObserved(_actor.getFatigue()),
            fatigue_capacity = wire.exactObserved(_actor.getFatigueMax()),
            head_armor = wire.exactObserved(_actor.getArmor(::Const.BodyPart.Head)),
            maximum_head_armor = wire.exactObserved(_actor.getArmorMax(::Const.BodyPart.Head)),
            body_armor = wire.exactObserved(_actor.getArmor(::Const.BodyPart.Body)),
            maximum_body_armor = wire.exactObserved(_actor.getArmorMax(::Const.BodyPart.Body)),
            morale = wire.exactObserved(_actor.getMoraleState()),
            initiative = wire.exactObserved(_actor.getInitiative())
        };
    },

    function _itemState(_actor, _item, _slot, _position)
    {
        local ammunition = wire.unknownValue();
        if ("getAmmo" in _item)
        {
            local ammo = _item.getAmmo();
            if (typeof ammo == "integer") ammunition = wire.exactObserved(ammo);
        }
        return {
            item_id = this.itemID(_actor, _item),
            content = wire.exactObserved(_item.getID()),
            slot = wire.exactObserved(this.slotLocation(_slot, _position)),
            membership = wire.exactObserved(true),
            condition = wire.exactObserved(_item.getCondition()),
            ammunition = ammunition
        };
    },

    function _ownedEquipment(_actor)
    {
        local ret = [];
        local data = _actor.getItems().m.Items;
        foreach (slot, entries in data)
        {
            foreach (position, item in entries)
            {
                if (item == null || item == -1 || item.isGarbage()) continue;
                ret.push(this._itemState(_actor, item, slot, position));
            }
        }
        ret.sort(@(a, b) a.item_id <=> b.item_id);
        return ret;
    },

    function _ownedSkills(_actor)
    {
        local ret = [];
        foreach (skill in _actor.getSkills().m.Skills)
        {
            if (skill == null || skill.isGarbage() || !skill.isActive() || skill.isHidden()) continue;
            local used = wire.unknownValue();
            if ("IsSpent" in skill.m && typeof skill.m.IsSpent == "bool")
                used = wire.exactObserved(skill.m.IsSpent);
            ret.push({
                skill_id = skill.getID(),
                possession = wire.exactObserved(true),
                enabled = wire.exactObserved(!skill.isDisabled()),
                cooldown = wire.unknownValue(),
                charges = wire.unknownValue(),
                used_this_turn = used
            });
        }
        ret.sort(@(a, b) a.skill_id <=> b.skill_id);
        return ret;
    },

    function _ownedEffects(_actor)
    {
        local ret = [];
        foreach (skill in _actor.getSkills().m.Skills)
        {
            if (skill == null || skill.isGarbage()) continue;
            local isEffect = skill.isType(::Const.SkillType.StatusEffect)
                || skill.isType(::Const.SkillType.Injury)
                || skill.isType(::Const.SkillType.PermanentInjury);
            if (!isEffect || skill.isHidden()) continue;
            ret.push({
                effect_id = skill.getID(),
                content = wire.exactObserved(skill.getID()),
                membership = wire.exactObserved(true),
                stacks = wire.unknownValue(),
                remaining_duration = wire.unknownValue()
            });
        }
        ret.sort(@(a, b) a.effect_id <=> b.effect_id);
        return ret;
    },

    function _skillIDList(_actor, _type)
    {
        local ret = [];
        foreach (skill in _actor.getSkills().m.Skills)
        {
            if (skill == null || skill.isGarbage() || !skill.isType(_type) || skill.isHidden()) continue;
            ret.push(skill.getID());
        }
        ret.sort();
        return ret;
    },

    function _ownedStats(_actor)
    {
        local p = _actor.getCurrentProperties();
        local ret = [
            { stat_id = "melee_skill", value = wire.exactObserved(p.getMeleeSkill()) },
            { stat_id = "ranged_skill", value = wire.exactObserved(p.getRangedSkill()) },
            { stat_id = "melee_defense", value = wire.exactObserved(p.getMeleeDefense()) },
            { stat_id = "ranged_defense", value = wire.exactObserved(p.getRangedDefense()) },
            { stat_id = "resolve", value = wire.exactObserved(p.getBravery()) }
        ];
        ret.sort(@(a, b) a.stat_id <=> b.stat_id);
        return ret;
    },

    function _relation(_active, _actor)
    {
        if (_actor.isPlayerControlled()) return "PLAYER";
        return _active.isAlliedWith(_actor) ? "ALLY" : "HOSTILE";
    },

    function _visibleToPlayer(_actor)
    {
        if (_actor.isPlayerControlled()) return true;
        if (!_actor.isAlive() || !_actor.isPlacedOnMap()) return false;
        return !_actor.isHiddenToPlayer() && _actor.getTile().IsVisibleForPlayer;
    },

    function _visibleActor(_raw, _active, _actor)
    {
        local actorId = this.actorID(_actor);
        local tileId = this.tileID(_actor.getTile());
        local owned = _actor.isPlayerControlled();
        local relation = this._relation(_active, _actor);
        local faction = "faction:" + _actor.getFaction();
        local actor = {
            actor_id = actorId,
            relation = relation,
            is_player_controlled = owned,
            life_state = _actor.isAlive() ? "ALIVE" : "REMOVED",
            visible = true,
            position = wire.exactObserved(tileId),
            resources = owned ? this._ownedResources(_actor) : this._unknownResources(),
            faction = owned ? wire.exactObserved(faction) : wire.observed(faction),
            content_identity = wire.unknownValue(),
            equipment = owned ? this._ownedEquipment(_actor) : [],
            effects = owned ? this._ownedEffects(_actor) : [],
            skills = owned ? this._ownedSkills(_actor) : [],
            tactical_stats = owned ? this._ownedStats(_actor) : [],
            perks = owned ? wire.exactObserved(this._skillIDList(_actor, ::Const.SkillType.Perk)) : wire.unknownValue(),
            traits = owned ? wire.exactObserved(this._skillIDList(_actor, ::Const.SkillType.Trait)) : wire.unknownValue(),
            last_seen = null
        };
        if (!owned)
        {
            capture.rememberPlayerLegalFact(
                "actor-memory:" + actorId,
                {
                    actor_id = actorId,
                    relation = relation,
                    faction = faction,
                    tile_id = tileId
                },
                _raw.ValidationContext.Round,
                _raw.SourceGeneration
            );
        }
        return actor;
    },

    function _rememberedActor(_fact)
    {
        local value = _fact.Value;
        return {
            actor_id = value.actor_id,
            relation = value.relation,
            is_player_controlled = false,
            life_state = "ALIVE",
            visible = false,
            position = wire.unknownValue(),
            resources = this._unknownResources(),
            faction = wire.remembered(value.faction, _fact.ObservedRound, _fact.ObservedDecision),
            content_identity = wire.unknownValue(),
            equipment = [], effects = [], skills = [], tactical_stats = [],
            perks = wire.unknownValue(), traits = wire.unknownValue(),
            last_seen = {
                tile_id = value.tile_id,
                observed_at = { round = _fact.ObservedRound, decision = _fact.ObservedDecision }
            }
        };
    },

    function _tileEffectFacts(_tile)
    {
        if (_tile.Properties.Effect == null) return [];
        local ret = [];
        foreach (key, value in _tile.Properties.Effect)
        {
            local kind = typeof value;
            if (kind != "null" && kind != "bool" && kind != "integer" && kind != "string") continue;
            ret.push(key + "=" + value);
        }
        ret.sort();
        return ret;
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

    function _coordinateMap()
    {
        local tileById = {};
        local ids = [];
        local size = ::Tactical.getMapSize();
        for (local x = 0; x < size.X; x = ++x)
        {
            for (local y = 0; y < size.Y; y = ++y)
            {
                if (!::Tactical.isValidTileSquare(x, y)) continue;
                local tile = ::Tactical.getTileSquare(x, y);
                local id = this.tileID(tile);
                tileById[id] <- tile;
                ids.push(id);
            }
        }
        ids.sort();
        local coords = {};
        local deltas = [[1, 0], [1, -1], [0, -1], [-1, 0], [-1, 1], [0, 1]];
        local native = this._nativeDirections();
        local component = 0;
        foreach (rootId in ids)
        {
            if (rootId in coords) continue;
            coords[rootId] <- { q = component * 1000, r = 0 };
            ++component;
            local queue = [rootId];
            local cursor = 0;
            while (cursor < queue.len())
            {
                local id = queue[cursor++];
                local tile = tileById[id];
                local here = coords[id];
                for (local direction = 0; direction < 6; direction = ++direction)
                {
                    local nativeDirection = native[direction];
                    if (!tile.hasNextTile(nativeDirection)) continue;
                    local nextTile = tile.getNextTile(nativeDirection);
                    if (nextTile == null) continue;
                    local nextId = this.tileID(nextTile);
                    if (!(nextId in tileById)) continue;
                    local expected = {
                        q = here.q + deltas[direction][0],
                        r = here.r + deltas[direction][1]
                    };
                    if (nextId in coords)
                    {
                        if (coords[nextId].q != expected.q || coords[nextId].r != expected.r)
                            throw "canonical tile topology is inconsistent";
                    }
                    else
                    {
                        coords[nextId] <- expected;
                        queue.push(nextId);
                    }
                }
            }
        }
        return coords;
    },

    function _visibleTileRecord(_raw, _tile, _coords)
    {
        local id = this.tileID(_tile);
        local neighborIds = array(6, null);
        local native = this._nativeDirections();
        for (local direction = 0; direction < 6; direction = ++direction)
        {
            if (!_tile.hasNextTile(native[direction])) continue;
            local neighbor = _tile.getNextTile(native[direction]);
            if (neighbor != null) neighborIds[direction] = this.tileID(neighbor);
        }
        local record = {
            tile_id = id,
            coordinate = _coords[id],
            elevation = _tile.Level,
            terrain = "bb_terrain:" + _tile.Type + ":" + _tile.Subtype,
            dynamic_effects = this._tileEffectFacts(_tile),
            neighbor_ids = neighborIds,
            observed_round = _raw.ValidationContext.Round,
            observed_decision = _raw.SourceGeneration
        };
        capture.rememberPlayerLegalFact(
            "tile-memory:" + id,
            record,
            _raw.ValidationContext.Round,
            _raw.SourceGeneration
        );
        return record;
    },

    function _tileFromRecord(_record, _visible, _included, _actorIds)
    {
        local neighbors = array(6, null);
        for (local i = 0; i < 6; i = ++i)
        {
            local id = _record.neighbor_ids[i];
            if (id != null && id in _included) neighbors[i] = id;
        }
        local terrain = _visible
            ? wire.exactObserved(_record.terrain)
            : wire.remembered(_record.terrain, _record.observed_round, _record.observed_decision);
        local effects = _visible
            ? wire.exactObserved(_record.dynamic_effects)
            : wire.remembered(_record.dynamic_effects, _record.observed_round, _record.observed_decision);
        return {
            tile_id = _record.tile_id,
            coordinate = _record.coordinate,
            elevation = _record.elevation,
            terrain = terrain,
            neighbors = neighbors,
            occupant_actor_id = _visible && _record.tile_id in _actorIds ? _actorIds[_record.tile_id] : null,
            blocking = wire.unknownValue(),
            visibility = _visible ? "EXACT_OBSERVED" : "REMEMBERED",
            dynamic_effects = effects,
            movement_cost = wire.unknownValue(),
            traversable = wire.unknownValue(),
            blocks_line_of_sight = wire.unknownValue()
        };
    },

    function build(_raw)
    {
        this._ensureBattle(_raw);
        local active = _raw.ActiveActor;
        local coords = this._coordinateMap();
        local actors = [];
        local actorByRuntimeID = {};
        local visibleActorIds = {};
        local actorByTile = {};

        local groups = _raw.EntityManager.getAllInstances();
        foreach (group in groups)
        {
            foreach (actor in group)
            {
                if (actor == null || actor.isNull() || !("isPlayerControlled" in actor)) continue;
                if (!this._visibleToPlayer(actor)) continue;
                local projected = this._visibleActor(_raw, active, actor);
                actors.push(projected);
                actorByRuntimeID[actor.getID().tostring()] <- projected.actor_id;
                visibleActorIds[projected.actor_id] <- true;
                actorByTile[projected.position.value] <- projected.actor_id;
            }
        }

        local memory = capture.getObservationMemory();
        foreach (key, fact in memory)
        {
            if (key.find("actor-memory:") != 0) continue;
            local actorId = fact.Value.actor_id;
            if (actorId in visibleActorIds) continue;
            actors.push(this._rememberedActor(fact));
        }
        actors.sort(@(a, b) a.actor_id <=> b.actor_id);

        local tileRecords = {};
        local tileVisible = {};
        local size = ::Tactical.getMapSize();
        for (local x = 0; x < size.X; x = ++x)
        {
            for (local y = 0; y < size.Y; y = ++y)
            {
                if (!::Tactical.isValidTileSquare(x, y)) continue;
                local tile = ::Tactical.getTileSquare(x, y);
                if (!tile.IsVisibleForPlayer) continue;
                local record = this._visibleTileRecord(_raw, tile, coords);
                tileRecords[record.tile_id] <- record;
                tileVisible[record.tile_id] <- true;
            }
        }
        memory = capture.getObservationMemory();
        foreach (key, fact in memory)
        {
            if (key.find("tile-memory:") != 0) continue;
            local record = fact.Value;
            if (!(record.tile_id in tileRecords)) tileRecords[record.tile_id] <- record;
        }

        local tiles = [];
        foreach (id, record in tileRecords)
            tiles.push(this._tileFromRecord(record, id in tileVisible, tileRecords, actorByTile));
        tiles.sort(@(a, b) a.tile_id <=> b.tile_id);

        local hostileFactions = {};
        local alliedFactions = {};
        foreach (actor in actors)
        {
            if (actor.faction.representation == "UNKNOWN") continue;
            local value = actor.faction.value;
            if (actor.relation == "HOSTILE") hostileFactions[value] <- true;
            else if (actor.relation == "ALLY") alliedFactions[value] <- true;
        }
        local hostile = [];
        local allied = [];
        foreach (id, _value in hostileFactions) hostile.push(id);
        foreach (id, _value in alliedFactions) allied.push(id);
        hostile.sort(); allied.sort();

        local turnEntries = [];
        local current = _raw.TurnSequenceBar.getCurrentEntities();
        local limit = ::Math.min(current.len(), _raw.TurnSequenceBar.m.MaxVisibleEntities);
        for (local i = 0; i < limit; i = ++i)
        {
            local actor = current[i];
            local key = actor.getID().tostring();
            if (!(key in actorByRuntimeID)) continue;
            turnEntries.push({
                actor_id = actorByRuntimeID[key],
                done = wire.exactObserved(false),
                sequence = wire.exactObserved(i)
            });
        }

        local activeId = this.actorID(active);
        return {
            state = {
                contract_version = wire.KernelIdentity.tactical_state,
                state_id = "",
                raw_capture_id = null,
                information_profile = "player_legal",
                ruleset = {
                    game_version = capture.SupportedGameVersion,
                    content_fingerprint = capture.RulesetContentFingerprint,
                    mods = []
                },
                battle = {
                    battle_id = "live-battle:" + _raw.BattleSequence,
                    player_faction_id = "faction:" + active.getFaction(),
                    phase = "COMBAT",
                    hostile_faction_ids = hostile,
                    allied_faction_ids = allied,
                    flags = []
                },
                decision = {
                    active_actor_id = activeId,
                    round = _raw.ValidationContext.Round,
                    decision_index = _raw.SourceGeneration,
                    actor_has_waited = active.isWaitActionSpent(),
                    actor_may_wait = _raw.TurnSequenceBar.canEntityWait(active) && active.isAbleToWait(),
                    turn_phase = "command_ready",
                    prior_action_ids = []
                },
                turn_state = { entries = turnEntries },
                environment = { light = "unknown", weather = null, effect_ids = [] },
                tiles = tiles,
                combatants = actors,
                action_affordances = null,
                ground_entities = [],
                annotations = null
            },
            runtime = {
                active_actor = active,
                active_actor_id = activeId,
                actor_by_runtime_id = actorByRuntimeID,
                tile_records = tileRecords,
                tile_visible = tileVisible
            }
        };
    }
};
