local wire = ::BBAGENT_Wire;

::BBAGENT_CanonicalIdentity <- {
    function _cloneJson(_value)
    {
        local kind = typeof _value;
        if (kind == "array")
        {
            local copy = [];
            foreach (child in _value) copy.push(this._cloneJson(child));
            return copy;
        }
        if (kind == "table")
        {
            local copy = {};
            foreach (key, child in _value) copy[key] <- this._cloneJson(child);
            return copy;
        }
        return _value;
    },

    function generationLabel(_battleSequence, _sourceGeneration)
    {
        return "live:" + _battleSequence + ":" + _sourceGeneration;
    },

    function _actionIntent(_action)
    {
        return {
            actor_id = _action.actor_id,
            kind = _action.kind,
            parameters = this._cloneJson(_action.parameters),
            skill_id = _action.skill_id,
            item_id = _action.item_id,
            target_kind = _action.target_kind,
            target_actor_id = _action.target_actor_id,
            target_tile_id = _action.target_tile_id,
            target_direction = _action.target_direction,
            mode_variant = _action.mode_variant,
            destination_tile_id = _action.destination_tile_id,
            resolved_path = this._cloneJson(_action.resolved_path),
            source_location = _action.source_location,
            target_slot = _action.target_slot,
            displaced_item_id = _action.displaced_item_id,
            displaced_item_destination = _action.displaced_item_destination
        };
    },

    function finalizeAction(_action)
    {
        _action.parameters.sort(@(a, b) a[0] <=> b[0]);
        _action.preview.facts.sort(@(a, b) a[0] <=> b[0]);
        if (_action.preview.affected_tile_ids != null)
        {
            local values = _action.preview.affected_tile_ids.value;
            values.sort();
            local unique = [];
            local prior = null;
            local hasPrior = false;
            foreach (value in values)
            {
                if (!hasPrior || value != prior) unique.push(value);
                prior = value;
                hasPrior = true;
            }
            _action.preview.affected_tile_ids.value = unique;
        }
        _action.action_id = "action:" + wire.canonicalHash(this._actionIntent(_action));
        return _action;
    },

    function _stripAuthority(_wrapper)
    {
        if (_wrapper != null && "authority" in _wrapper) delete _wrapper.authority;
    },

    function _identityState(_state)
    {
        local identity = this._cloneJson(_state);
        delete identity.state_id;
        delete identity.raw_capture_id;
        delete identity.annotations;

        local affordances = identity.action_affordances;
        delete affordances.captured_for_state_id;
        delete affordances.source_generation;
        foreach (action in affordances.actions)
        {
            if (action.contingent_reactions.len() == 0) delete action.contingent_reactions;
            delete action.debug_ground_truth;
            delete action.source_generation;
            delete action.provenance;
            this._stripAuthority(action.ap_cost);
            this._stripAuthority(action.fatigue_cost);
            this._stripAuthority(action.charge_cost);
            this._stripAuthority(action.ammo_cost);
            this._stripAuthority(action.item_action_cost);
            this._stripAuthority(action.preview.displayed_hit_chance);
            this._stripAuthority(action.preview.displayed_damage);
            this._stripAuthority(action.preview.affected_tile_ids);
            foreach (fact in action.preview.facts) this._stripAuthority(fact[1]);
        }
        return identity;
    },

    function finalizeState(_state, _actions, _battleSequence, _sourceGeneration)
    {
        local generation = this.generationLabel(_battleSequence, _sourceGeneration);
        local unique = {};
        foreach (action in _actions)
        {
            action.source_generation = generation;
            this.finalizeAction(action);
            if (action.action_id in unique)
            {
                if (wire.canonicalJson(unique[action.action_id]) != wire.canonicalJson(action))
                    throw "conflicting affordances share an action_id";
                continue;
            }
            unique[action.action_id] <- action;
        }
        local actionIds = [];
        foreach (actionId, _action in unique) actionIds.push(actionId);
        actionIds.sort();
        local actions = [];
        foreach (actionId in actionIds) actions.push(unique[actionId]);
        if (actions.len() == 0) throw "complete live affordance set cannot be empty";

        _state.action_affordances = {
            actor_id = _state.decision.active_actor_id,
            captured_for_state_id = "",
            source_generation = generation,
            completeness = "COMPLETE",
            actions = actions
        };
        local stateId = wire.canonicalHash(this._identityState(_state));
        _state.state_id = stateId;
        _state.action_affordances.captured_for_state_id = stateId;
        return _state;
    }
};
