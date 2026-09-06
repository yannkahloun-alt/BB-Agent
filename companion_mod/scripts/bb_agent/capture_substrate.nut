::BBAGENT_Capture <- {
    CaptureContractVersion = "bb-agent-live-capture.v1",
    SupportedScriptsRevision = "162f498ac7c49b4c317bbf54718a595ecef6a65a",
    SupportedGameVersion = "scripts-162f498ac7c49b4c317bbf54718a595ecef6a65a",
    RulesetContentFingerprint = "4c4b714832d1989740a6f07dce058c11aa1e9123056966ede06ce42d1df182bd",

    State = {
        BattleSequence = 0,
        SourceGeneration = -1,
        IsReady = false,
        LastReadySignature = null,
        CurrentRaw = null,
        LastEvent = null,
        LastError = null,
        ObservationMemory = {},
        Provenance = {
            GameVersion = "scripts-162f498ac7c49b4c317bbf54718a595ecef6a65a",
            RulesetGameVersion = "scripts-162f498ac7c49b4c317bbf54718a595ecef6a65a",
            RulesetContentFingerprint = "4c4b714832d1989740a6f07dce058c11aa1e9123056966ede06ce42d1df182bd",
            Mods = []
        }
    },

    function _copyArray(_values)
    {
        local ret = [];
        foreach (value in _values) ret.push(value);
        return ret;
    },

    function configureProvenance(_gameVersion, _rulesetGameVersion, _contentFingerprint, _mods)
    {
        if (_gameVersion == null || _gameVersion == "") throw "game version is required";
        if (_rulesetGameVersion == null || _rulesetGameVersion == "") throw "ruleset game version is required";
        if (_contentFingerprint == null || _contentFingerprint == "") throw "content fingerprint is required";

        local mods = this._copyArray(_mods);
        mods.sort();
        this.State.Provenance = {
            GameVersion = _gameVersion,
            RulesetGameVersion = _rulesetGameVersion,
            RulesetContentFingerprint = _contentFingerprint,
            Mods = mods
        };
    },

    function beginBattle()
    {
        ++this.State.BattleSequence;
        this.State.SourceGeneration = -1;
        this.State.IsReady = false;
        this.State.LastReadySignature = null;
        this.State.CurrentRaw = null;
        this.State.LastEvent = null;
        this.State.LastError = null;
        this.State.ObservationMemory = {};
        ::logInfo("[BB-Agent Capture] battle=" + this.State.BattleSequence + " capture initialized");
    },

    function endBattle(_reason = "battle_ended")
    {
        this.invalidate(_reason);
        this.State.CurrentRaw = null;
        this.State.ObservationMemory = {};
    },

    function invalidate(_reason)
    {
        if (!this.State.IsReady) return this.State.LastEvent;

        this.State.IsReady = false;
        this.State.CurrentRaw = null;
        this.State.LastEvent = {
            RecordType = "DECISION_INVALIDATED",
            BattleSequence = this.State.BattleSequence,
            SourceGeneration = this.State.SourceGeneration,
            Reason = _reason
        };
        ::logInfo(
            "[BB-Agent Capture] INVALIDATED battle=" + this.State.BattleSequence
            + " generation=" + this.State.SourceGeneration
            + " reason=" + _reason
        );
        return this.State.LastEvent;
    },

    function getCurrentRawAcquisition()
    {
        return this.State.IsReady ? this.State.CurrentRaw : null;
    },

    function getLastLifecycleEvent()
    {
        return this.State.LastEvent;
    },

    function getHealth()
    {
        return {
            BattleSequence = this.State.BattleSequence,
            SourceGeneration = this.State.SourceGeneration,
            IsReady = this.State.IsReady,
            LastError = this.State.LastError
        };
    },

    function getObservationMemory()
    {
        return this.State.ObservationMemory;
    },

    // #57 may call this only with facts already projected through player_legal policy.
    // Raw runtime objects must never be inserted into ObservationMemory.
    function rememberPlayerLegalFact(_key, _value, _round, _decision)
    {
        if (_key == null || _key == "") throw "observation-memory key is required";
        this.State.ObservationMemory[_key] <- {
            Value = _value,
            ObservedRound = _round,
            ObservedDecision = _decision
        };
    },

    function forgetPlayerLegalFact(_key)
    {
        if (_key in this.State.ObservationMemory) delete this.State.ObservationMemory[_key];
    },

    function _commandReadiness(_state)
    {
        if (_state == null) return { Ready = false, Reason = "no_tactical_state" };
        if (_state.isBattleEnded()) return { Ready = false, Reason = "battle_ended" };
        if (_state.isPaused()) return { Ready = false, Reason = "paused" };
        if (!("TurnSequenceBar" in ::Tactical) || ::Tactical.TurnSequenceBar == null)
            return { Ready = false, Reason = "turn_sequence_unavailable" };

        local active = ::Tactical.TurnSequenceBar.getActiveEntity();
        if (active == null) return { Ready = false, Reason = "no_active_actor" };
        if (!active.isAlive() || !active.isPlacedOnMap() || !active.isPlayerControlled())
            return { Ready = false, Reason = "active_actor_not_player_ready" };
        if (!active.isTurnStarted() || active.isTurnDone())
            return { Ready = false, Reason = "active_actor_turn_not_open" };
        if (_state.isInputLocked()) return { Ready = false, Reason = "input_locked" };
        if (_state.getCurrentActionState() != null)
            return { Ready = false, Reason = "action_state_active" };
        if (active.getSkills().isBusy()) return { Ready = false, Reason = "skills_busy" };
        if (::Tactical.getNavigator().isTravelling(active))
            return { Ready = false, Reason = "navigator_travelling" };
        if (::Time.hasEventScheduled(::TimeUnit.Virtual))
            return { Ready = false, Reason = "virtual_event_pending" };
        if (_state.m.IsShowingFleeScreen || _state.m.IsExitingToMenu)
            return { Ready = false, Reason = "modal_tactical_state" };

        return { Ready = true, Reason = null, Active = active };
    },

    function _boolToken(_value)
    {
        return _value ? "1" : "0";
    },

    function _tileToken(_actor)
    {
        if (!_actor.isPlacedOnMap()) return "tile:none";
        local tile = _actor.getTile();
        return "tile:" + tile.SquareCoords.X + ":" + tile.SquareCoords.Y + ":" + tile.Level;
    },

    function _skillTokens(_actor)
    {
        local ret = [];
        foreach (skill in _actor.getSkills().m.Skills)
        {
            if (skill == null || skill.isGarbage()) continue;
            ret.push(skill.getID() + ":hidden=" + this._boolToken(skill.isHidden()));
        }
        ret.sort();
        return ret;
    },

    function _itemTokens(_actor)
    {
        local ret = [];
        foreach (item in _actor.getItems().getAllItems())
        {
            if (item == null || item == -1 || item.isGarbage()) continue;
            ret.push(
                item.getID()
                + ":slot=" + item.getCurrentSlotType()
                + ":condition=" + item.getCondition()
            );
        }
        ret.sort();
        return ret;
    },

    function _actorToken(_actor)
    {
        local tokens = [
            "actor=" + _actor.getID(),
            "faction=" + _actor.getFaction(),
            "alive=" + this._boolToken(_actor.isAlive()),
            "placed=" + this._boolToken(_actor.isPlacedOnMap()),
            this._tileToken(_actor),
            "hp=" + _actor.getHitpoints(),
            "hpmax=" + _actor.getHitpointsMax(),
            "ap=" + _actor.getActionPoints(),
            "fatigue=" + _actor.getFatigue(),
            "fatiguemax=" + _actor.getFatigueMax(),
            "morale=" + _actor.getMoraleState(),
            "waitspent=" + this._boolToken(_actor.isWaitActionSpent()),
            "turnstarted=" + this._boolToken(_actor.isTurnStarted()),
            "turndone=" + this._boolToken(_actor.isTurnDone())
        ];

        foreach (skill in this._skillTokens(_actor)) tokens.push("skill=" + skill);
        foreach (item in this._itemTokens(_actor)) tokens.push("item=" + item);
        tokens.sort();
        return tokens.join(",");
    },

    function _entityTokens()
    {
        local ret = [];
        local groups = ::Tactical.Entities.getAllInstances();
        foreach (group in groups)
        {
            foreach (actor in group)
            {
                if (actor == null || actor.isNull()) continue;
                ret.push(this._actorToken(actor));
            }
        }
        ret.sort();
        return ret;
    },

    function _turnSequenceTokens()
    {
        local ret = [];
        local entities = ::Tactical.TurnSequenceBar.getCurrentEntities();
        foreach (index, actor in entities)
        {
            if (actor == null || actor.isNull()) continue;
            ret.push("turn=" + index + ":" + actor.getID());
        }
        return ret;
    },

    function _mapTokens()
    {
        local ret = [];
        local size = ::Tactical.getMapSize();
        for (local x = 0; x < size.X; x = ++x)
        {
            for (local y = 0; y < size.Y; y = ++y)
            {
                if (!::Tactical.isValidTileSquare(x, y)) continue;
                local tile = ::Tactical.getTileSquare(x, y);
                ret.push(
                    "map=" + x + ":" + y
                    + ":level=" + tile.Level
                    + ":type=" + tile.Type
                    + ":subtype=" + tile.Subtype
                    + ":empty=" + this._boolToken(tile.IsEmpty)
                    + ":visible=" + this._boolToken(tile.IsVisibleForPlayer)
                    + ":discovered=" + this._boolToken(tile.IsDiscovered)
                );
            }
        }
        return ret;
    },

    function _fingerprintInputs(_state, _active)
    {
        local turnBar = ::Tactical.TurnSequenceBar;
        local ret = [
            "capture_contract=" + this.CaptureContractVersion,
            "game_version=" + this.State.Provenance.GameVersion,
            "ruleset_game_version=" + this.State.Provenance.RulesetGameVersion,
            "ruleset_content=" + this.State.Provenance.RulesetContentFingerprint,
            "battle=" + this.State.BattleSequence,
            "round=" + turnBar.getCurrentRound(),
            "turn_position=" + turnBar.getTurnPosition(),
            "active_actor=" + _active.getID(),
            "waitspent=" + this._boolToken(_active.isWaitActionSpent()),
            "turnstarted=" + this._boolToken(_active.isTurnStarted())
        ];

        foreach (modID in this.State.Provenance.Mods) ret.push("mod=" + modID);
        foreach (actorToken in this._entityTokens()) ret.push("entity=" + actorToken);
        foreach (turnToken in this._turnSequenceTokens()) ret.push(turnToken);
        foreach (mapToken in this._mapTokens()) ret.push(mapToken);
        ret.sort();
        return ret;
    },

    function _sourceSignature(_inputs)
    {
        // Internal duplicate-comparison material only. #57 converts these stable
        // inputs into the frozen external SHA-256 raw_source_fingerprint.
        return _inputs.join("\x1f");
    },

    function _acquireRaw(_state, _active, _fingerprintInputs)
    {
        return {
            CaptureContractVersion = this.CaptureContractVersion,
            Provenance = this.State.Provenance,
            BattleSequence = this.State.BattleSequence,
            SourceGeneration = this.State.SourceGeneration,
            ValidationContext = {
                Round = ::Tactical.TurnSequenceBar.getCurrentRound(),
                TurnPosition = ::Tactical.TurnSequenceBar.getTurnPosition(),
                ActiveActorID = _active.getID(),
                WaitSpent = _active.isWaitActionSpent(),
                TurnStarted = _active.isTurnStarted()
            },
            RawSourceFingerprintInputs = _fingerprintInputs,
            ActiveActor = _active,
            TacticalState = _state,
            TurnSequenceBar = ::Tactical.TurnSequenceBar,
            EntityManager = ::Tactical.Entities,
            Navigator = ::Tactical.getNavigator()
        };
    },

    function observe(_state)
    {
        try
        {
            local readiness = this._commandReadiness(_state);
            if (!readiness.Ready)
            {
                this.invalidate(readiness.Reason);
                return this.State.LastEvent;
            }

            local wasReady = this.State.IsReady;
            local active = readiness.Active;
            local inputs = this._fingerprintInputs(_state, active);
            local signature = this._sourceSignature(inputs);
            local duplicate = this.State.LastReadySignature != null
                && this.State.LastReadySignature == signature;

            // An unchanged source on an uninterrupted ready frame is not a new
            // lifecycle event. The same unchanged source after INVALIDATED is a
            // deliberate duplicate READY re-emission on the same generation.
            if (duplicate && wasReady) return null;

            if (!duplicate)
            {
                ++this.State.SourceGeneration;
                this.State.LastReadySignature = signature;
            }

            local raw = this._acquireRaw(_state, active, inputs);
            raw.SourceGeneration = this.State.SourceGeneration;
            this.State.CurrentRaw = raw;
            this.State.IsReady = true;
            this.State.LastError = null;
            this.State.LastEvent = {
                RecordType = "DECISION_READY",
                BattleSequence = this.State.BattleSequence,
                SourceGeneration = this.State.SourceGeneration,
                Duplicate = duplicate,
                ActiveActorID = active.getID(),
                Round = ::Tactical.TurnSequenceBar.getCurrentRound(),
                TurnPosition = ::Tactical.TurnSequenceBar.getTurnPosition()
            };

            if (!duplicate)
            {
                ::logInfo(
                    "[BB-Agent Capture] READY battle=" + this.State.BattleSequence
                    + " generation=" + this.State.SourceGeneration
                    + " actor=" + active.getID()
                );
            }
            return this.State.LastEvent;
        }
        catch (error)
        {
            this.State.LastError = error.tostring();
            this.invalidate("capture_error");
            ::logError("[BB-Agent Capture] capture_error; advice invalidated");
            return this.State.LastEvent;
        }
    }
};
