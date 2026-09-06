local wire = ::BBAGENT_Wire;
local legal = ::BBAGENT_PlayerLegal;

::BBAGENT_Affordances <- {
    function _zeroCost()
    {
        return wire.resolvedCost(0);
    },

    function _preview(_hitChance = null)
    {
        return {
            displayed_hit_chance = _hitChance,
            affected_tile_ids = null,
            displayed_damage = null,
            facts = []
        };
    },

    function _baseAction(_actorId, _kind)
    {
        return {
            action_id = "",
            actor_id = _actorId,
            kind = _kind,
            provenance = "GAME_PLAYER_AFFORDANCE",
            source_generation = "",
            parameters = [],
            ap_cost = null,
            fatigue_cost = null,
            charge_cost = null,
            ammo_cost = null,
            item_action_cost = null,
            skill_id = null,
            item_id = null,
            target_kind = null,
            target_actor_id = null,
            target_tile_id = null,
            target_direction = null,
            mode_variant = null,
            destination_tile_id = null,
            resolved_path = [],
            source_location = null,
            target_slot = null,
            displaced_item_id = null,
            displaced_item_destination = null,
            preview = this._preview(),
            debug_ground_truth = null,
            contingent_reactions = []
        };
    },

    function _resolvedCosts(_action, _ap, _fatigue, _ammo = 0, _charge = 0, _itemAction = 0)
    {
        _action.ap_cost = wire.resolvedCost(_ap);
        _action.fatigue_cost = wire.resolvedCost(_fatigue);
        _action.charge_cost = wire.resolvedCost(_charge);
        _action.ammo_cost = wire.resolvedCost(_ammo);
        _action.item_action_cost = wire.resolvedCost(_itemAction);
        return _action;
    },

    function _skillResourceCosts(_active, _skill)
    {
        local item = _skill.getItem();
        if (item != null && item.isItemType(::Const.Items.ItemType.Usable)
            && !item.isItemType(::Const.Items.ItemType.Weapon))
        {
            throw "legal consumable skill has no canonical charge/item resource extractor";
        }
        if (!("consumeAmmo" in _skill))
            return { ammo = 0, charge = 0, item_action = 0 };

        local source = null;
        if (item != null && "getAmmoMax" in item && "getAmmoCost" in item
            && item.getAmmoMax() > 0)
        {
            source = item;
        }
        else
        {
            local ammoItem = _active.getItems().getItemAtSlot(::Const.ItemSlot.Ammo);
            if (ammoItem != null && "getAmmo" in ammoItem && "getAmmoCost" in ammoItem)
                source = ammoItem;
        }
        if (source == null)
            throw "legal ammo-consuming skill has no supported player-visible ammo source";
        local ammo = source.getAmmoCost();
        if (typeof ammo != "integer" || ammo < 0)
            throw "ammo source returned an invalid canonical cost";
        return { ammo = ammo, charge = 0, item_action = 0 };
    },

    function _visibleTargetTiles(_projection)
    {
        local ret = [];
        local size = ::Tactical.getMapSize();
        for (local x = 0; x < size.X; x = ++x)
        {
            for (local y = 0; y < size.Y; y = ++y)
            {
                if (!::Tactical.isValidTileSquare(x, y)) continue;
                local tile = ::Tactical.getTileSquare(x, y);
                local id = legal.tileID(tile);
                if (!tile.IsVisibleForPlayer || !(id in _projection.runtime.tile_visible)) continue;
                ret.push(tile);
            }
        }
        ret.sort(@(a, b) legal.tileID(a) <=> legal.tileID(b));
        return ret;
    },

    function _affectedTilePreview(_skill, _targetTile, _projection)
    {
        if (!_skill.isAOE()) return null;
        local ids = [];
        foreach (tile in _skill.getAffectedTiles(_targetTile))
        {
            if (tile == null) continue;
            local id = legal.tileID(tile);
            if (!(id in _projection.runtime.tile_records))
                throw "player-visible AOE preview references a tile outside canonical projection";
            ids.push(id);
        }
        ids.sort();
        return wire.resolvedPreview(ids);
    },

    function _skillActions(_raw, _projection)
    {
        local ret = [];
        local active = _raw.ActiveActor;
        local actorId = _projection.runtime.active_actor_id;
        local targetTiles = this._visibleTargetTiles(_projection);
        foreach (skill in active.getSkills().queryActives())
        {
            if (!skill.isUsable() || !skill.isAffordable()) continue;
            local resources = this._skillResourceCosts(active, skill);
            if (!skill.isTargeted())
            {
                local action = this._baseAction(actorId, "USE_SKILL");
                action.skill_id = skill.getID();
                action.target_kind = "SELF";
                this._resolvedCosts(
                    action,
                    skill.getActionPointCost(),
                    skill.getFatigueCost(),
                    resources.ammo,
                    resources.charge,
                    resources.item_action
                );
                ret.push(action);
                continue;
            }

            if (!skill.isVisibleTileNeeded())
                throw "legal targeted skill can select non-visible tiles outside the current canonical subset";

            foreach (tile in targetTiles)
            {
                if (!skill.isUsableOn(tile, active.getTile())) continue;
                local action = this._baseAction(actorId, "USE_SKILL");
                action.skill_id = skill.getID();
                if (skill.isTargetingActor())
                {
                    if (tile.IsEmpty) throw "actor-targeted legal skill resolved to an empty tile";
                    local target = tile.getEntity();
                    if (target == null || target.isHiddenToPlayer())
                        throw "legal actor target is not player-visible";
                    local runtimeId = target.getID().tostring();
                    if (!(runtimeId in _projection.runtime.actor_by_runtime_id))
                        throw "legal actor target is absent from player-legal projection";
                    action.target_kind = "ACTOR";
                    action.target_actor_id = _projection.runtime.actor_by_runtime_id[runtimeId];
                    if (skill.isUsingHitchance())
                    {
                        local chance = skill.getHitchance(target);
                        if (typeof chance != "integer" || chance < 0 || chance > 100)
                            throw "player-visible hit chance is outside canonical integer bounds";
                        action.preview.displayed_hit_chance = wire.resolvedPreview(chance);
                    }
                }
                else
                {
                    action.target_kind = skill.isAOE() ? "AREA" : "TILE";
                    action.target_tile_id = legal.tileID(tile);
                }
                action.preview.affected_tile_ids = this._affectedTilePreview(skill, tile, _projection);
                this._resolvedCosts(
                    action,
                    skill.getActionPointCost(),
                    skill.getFatigueCost(),
                    resources.ammo,
                    resources.charge,
                    resources.item_action
                );
                ret.push(action);
            }
        }
        return ret;
    },

    function _movementSettings(_active, _navigator)
    {
        local settings = _navigator.createSettings();
        settings.ActionPointCosts = _active.getActionPointCosts();
        settings.FatigueCosts = _active.getFatigueCosts();
        settings.FatigueCostFactor = ::Const.Movement.FatigueCostFactor;
        settings.ActionPointCostPerLevel = _active.getLevelActionPointCost();
        settings.FatigueCostPerLevel = _active.getLevelFatigueCost();
        settings.ZoneOfControlCost = 4;
        settings.AlliedFactions = _active.getAlliedFactions();
        settings.Faction = _active.getFaction();
        settings.AllowZoneOfControlPassing = true;
        settings.IsPlayer = true;
        return settings;
    },

    function _pathTile(_entry)
    {
        if (_entry == null) return null;
        if ("SquareCoords" in _entry) return _entry;
        if ("Tile" in _entry && _entry.Tile != null) return _entry.Tile;
        if ("getTile" in _entry) return _entry.getTile();
        return null;
    },

    function _navigatorPath(_navigator, _origin, _destination)
    {
        local path = null;
        if ("getPath" in _navigator) path = _navigator.getPath();
        else if ("Path" in _navigator) path = _navigator.Path;
        else if ("m" in _navigator && "Path" in _navigator.m) path = _navigator.m.Path;
        if (path == null || typeof path != "array")
            throw "native navigator path is not exposed through a supported read-only accessor";

        local tiles = [];
        foreach (entry in path)
        {
            local tile = this._pathTile(entry);
            if (tile == null) throw "native navigator path contains an unknown node shape";
            tiles.push(tile);
        }
        if (tiles.len() != 0 && legal.tileID(tiles[0]) == legal.tileID(_destination)) tiles.reverse();
        if (tiles.len() != 0 && legal.tileID(tiles[0]) == legal.tileID(_origin)) tiles.remove(0);
        if (tiles.len() == 0 || legal.tileID(tiles[tiles.len() - 1]) != legal.tileID(_destination))
            throw "native navigator path does not terminate at requested destination";
        return tiles;
    },

    function _visibleHostileReactors(_state, _originTile)
    {
        local neighbors = {};
        local originId = legal.tileID(_originTile);
        foreach (tile in _state.tiles)
        {
            if (tile.tile_id != originId) continue;
            foreach (neighbor in tile.neighbors) if (neighbor != null) neighbors[neighbor] <- true;
            break;
        }
        local ret = [];
        foreach (actor in _state.combatants)
        {
            if (actor.relation != "HOSTILE" || !actor.visible || actor.life_state != "ALIVE") continue;
            if (actor.position.representation != "EXACT") continue;
            if (actor.position.value in neighbors) ret.push(actor.actor_id);
        }
        ret.sort();
        return ret;
    },

    function _aooReactions(_state, _active, _pathTiles)
    {
        local reactions = [];
        local origin = _active.getTile();
        foreach (step in _pathTiles)
        {
            local count = origin.getZoneOfControlCountOtherThan(_active.getAlliedFactions());
            if (count > 0)
            {
                local reactors = this._visibleHostileReactors(_state, origin);
                if (reactors.len() != count)
                    throw "player-visible ZOC count cannot be reconciled to visible reacting actors";
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
            }
            origin = step;
        }
        return reactions;
    },

    function _moveActions(_raw, _projection)
    {
        local ret = [];
        local active = _raw.ActiveActor;
        local actorId = _projection.runtime.active_actor_id;
        local navigator = _raw.Navigator;
        local targetTiles = this._visibleTargetTiles(_projection);
        foreach (destination in targetTiles)
        {
            if (destination.ID == active.getTile().ID) continue;
            navigator.clearPath();
            navigator.clearVisualisation();
            local settings = this._movementSettings(active, navigator);
            local found = false;
            local costs = null;
            local pathTiles = null;
            try
            {
                found = navigator.findPath(active.getTile(), destination, settings, 0);
                if (found)
                {
                    settings.ZoneOfControlCost = 0;
                    costs = navigator.getCostForPath(
                        active,
                        settings,
                        active.getActionPoints(),
                        active.getFatigueMax() - active.getFatigue()
                    );
                    if (costs.Tiles != 0) pathTiles = this._navigatorPath(navigator, active.getTile(), destination);
                }
            }
            catch (error)
            {
                navigator.clearPath();
                navigator.clearVisualisation();
                throw error;
            }
            navigator.clearPath();
            navigator.clearVisualisation();
            if (!found || costs == null || costs.Tiles == 0) continue;
            if (typeof costs.ActionPoints != "integer" || typeof costs.Fatigue != "integer")
                throw "native movement preview returned non-integer canonical costs";

            local action = this._baseAction(actorId, "MOVE_TO");
            action.destination_tile_id = legal.tileID(destination);
            foreach (tile in pathTiles) action.resolved_path.push(legal.tileID(tile));
            action.contingent_reactions = this._aooReactions(_projection.state, active, pathTiles);
            this._resolvedCosts(action, costs.ActionPoints, costs.Fatigue);
            ret.push(action);
        }
        return ret;
    },

    function _waitAndEndTurn(_raw, _projection)
    {
        local ret = [];
        local active = _raw.ActiveActor;
        local actorId = _projection.runtime.active_actor_id;
        if (_raw.TurnSequenceBar.canEntityWait(active) && active.isAbleToWait())
        {
            local wait = this._baseAction(actorId, "WAIT");
            this._resolvedCosts(wait, 0, 0);
            ret.push(wait);
        }
        local endTurn = this._baseAction(actorId, "END_TURN");
        this._resolvedCosts(endTurn, 0, 0);
        ret.push(endTurn);
        return ret;
    },

    function _equipActions(_raw, _projection)
    {
        local ret = [];
        local active = _raw.ActiveActor;
        local actorId = _projection.runtime.active_actor_id;
        local inventory = active.getItems();
        local screen = _raw.TacticalState.m.CharacterScreen;
        if (screen == null) throw "tactical character-screen inventory authority is unavailable";
        local bag = inventory.m.Items[::Const.ItemSlot.Bag];
        local unlocked = inventory.getUnlockedBagSlots();
        for (local position = 0; position < ::Math.min(bag.len(), unlocked); position = ++position)
        {
            local item = bag[position];
            if (item == null || item == -1 || item.isGarbage()) continue;
            if (item.getSlotType() == ::Const.ItemSlot.Bag || !item.isChangeableInBattle()) continue;

            local target = screen.helper_queryEquipmentTargetItems(inventory, item);
            local items = [item, target.firstItem, target.secondItem];
            local blocked = screen.helper_isActionAllowed(active, items, false);
            if (blocked != null || !inventory.isActionAffordable(items)) continue;
            if (inventory.getNumberOfEmptySlots(::Const.ItemSlot.Bag) < target.slotsNeeded - 1) continue;
            if (target.secondItem != null)
                throw "legal equipment command has two displaced items and is not canonically representable";

            local action = this._baseAction(actorId, "EQUIP_ITEM");
            action.item_id = legal.itemID(active, item);
            action.source_location = "bag:" + position;
            action.target_slot = legal._slotName(item.getSlotType());
            if (target.firstItem != null)
            {
                action.displaced_item_id = legal.itemID(active, target.firstItem);
                action.displaced_item_destination = action.source_location;
            }
            local cost = inventory.getActionCost(items);
            if (typeof cost != "integer" || cost < 0)
                throw "inventory authority returned an invalid switch AP cost";
            this._resolvedCosts(action, cost, 0, 0, 0, 0);
            ret.push(action);
        }
        return ret;
    },

    function acquire(_raw, _projection)
    {
        local actions = [];
        actions.extend(this._skillActions(_raw, _projection));
        actions.extend(this._moveActions(_raw, _projection));
        actions.extend(this._equipActions(_raw, _projection));
        actions.extend(this._waitAndEndTurn(_raw, _projection));
        return actions;
    }
};
