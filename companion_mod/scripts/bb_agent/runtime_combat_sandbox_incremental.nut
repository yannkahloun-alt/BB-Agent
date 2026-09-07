local sandbox = ::BBAGENT_CombatSandbox;
local capture = ::BBAGENT_Capture;
local wire = ::BBAGENT_Wire;
local oracle = ::BBAGENT_DebugOracle;

// Full forensic capture is deliberately spread across real-time callbacks.
// Using TimeUnit.Real avoids tripping the normal READY guard that rejects
// pending Virtual-time gameplay events. One logical record is built/emitted
// per slice initially; breadth is preserved while frame stalls are bounded.
sandbox.BatchDelayMs <- 8;
sandbox.BatchRecordsPerTick <- 1;
sandbox.RawInputBatchSize <- 24;
sandbox.ActiveJob <- null;

sandbox._scheduleBatch <- function(_job)
{
    ::Time.scheduleEvent(
        ::TimeUnit.Real,
        this.BatchDelayMs,
        sandbox._runBatch.bindenv(sandbox),
        _job
    );
};

sandbox._pushTask <- function(_tasks, _kind, _section, _key, _extra = null)
{
    _tasks.push({
        kind = _kind,
        section = _section,
        key = _key,
        extra = _extra
    });
};

sandbox._fieldTasks <- function(_tasks, _kind, _section, _state)
{
    if (_state == null) return;
    local entries = [];
    try
    {
        foreach (key, _value in _state)
            entries.push({ name = key.tostring(), key = key });
    }
    catch (_error)
    {
        return;
    }
    entries.sort(@(a, b) a.name <=> b.name);
    foreach (index, entry in entries)
    {
        this._pushTask(
            _tasks,
            _kind,
            _section,
            index.tostring(),
            { state = _state, field_key = entry.key, field_name = entry.name }
        );
    }
};

sandbox._actorCorePayload <- function(_actor, _active)
{
    local placed = false;
    try { placed = _actor.isPlacedOnMap(); } catch (_error) {}
    local tileId = null;
    if (placed)
    {
        try { tileId = this._tileID(_actor.getTile()); } catch (_error) {}
    }

    local hidden = null;
    try { hidden = _actor.isHiddenToPlayer(); } catch (_error) {}
    local alliedWithActive = null;
    try { alliedWithActive = _active.isAlliedWith(_actor); } catch (_error) {}
    local faction = null;
    try { faction = _actor.getFaction(); } catch (_error) {}
    local aooSkill = null;
    try
    {
        local attack = _actor.getSkills().getAttackOfOpportunity();
        if (attack != null) aooSkill = attack.getID();
    }
    catch (_error) {}

    local record = {
        runtime_id = _actor.getID().tostring(),
        canonical_actor_id = this._actorID(_actor),
        name = this._tryActorName(_actor),
        title = this._tryActorTitle(_actor),
        faction = faction,
        allied_with_active = alliedWithActive,
        is_player_controlled = _actor.isPlayerControlled(),
        hidden_to_player = hidden,
        alive = _actor.isAlive(),
        placed_on_map = placed,
        tile_id = tileId,
        type = this._tryEntityType(_actor),
        hitpoints = _actor.getHitpoints(),
        hitpoints_max = _actor.getHitpointsMax(),
        armor_head = _actor.getArmor(::Const.BodyPart.Head),
        armor_body = _actor.getArmor(::Const.BodyPart.Body),
        action_points = _actor.getActionPoints(),
        action_points_max = _actor.getActionPointsMax(),
        fatigue = _actor.getFatigue(),
        fatigue_max = _actor.getFatigueMax(),
        morale_state = _actor.getMoraleState(),
        initiative = _actor.getInitiative(),
        wait_spent = _actor.isWaitActionSpent(),
        turn_started = _actor.isTurnStarted(),
        turn_done = _actor.isTurnDone(),
        movement_ap_costs = this._reflect(_actor.getActionPointCosts()),
        movement_fatigue_costs = this._reflect(_actor.getFatigueCosts()),
        level_action_point_cost = _actor.getLevelActionPointCost(),
        level_fatigue_cost = _actor.getLevelFatigueCost(),
        max_traversible_levels = _actor.getMaxTraversibleLevels(),
        attack_of_opportunity_skill_id = aooSkill
    };
    try { record.has_zone_of_control <- _actor.hasZoneOfControl(); } catch (_error) {}
    try { record.exerting_zone_of_control <- _actor.isExertingZoneOfControl(); } catch (_error) {}
    try { record.allied_factions <- this._reflect(_actor.getAlliedFactions()); } catch (_error) {}
    return record;
};

sandbox._playerLegalMeta <- function(_projection)
{
    local state = _projection.state;
    return {
        contract_version = state.contract_version,
        state_id = state.state_id,
        raw_capture_id = state.raw_capture_id,
        information_profile = state.information_profile,
        ruleset = state.ruleset,
        battle = state.battle,
        decision = state.decision,
        turn_state = state.turn_state,
        environment = state.environment,
        action_affordances = state.action_affordances,
        ground_entities = state.ground_entities,
        annotations = state.annotations
    };
};

sandbox._buildJob <- function(_raw, _projection)
{
    local tasks = [];
    this._pushTask(tasks, "raw_root", "raw", "root");

    local rawInputs = _raw.RawSourceFingerprintInputs;
    for (local start = 0; start < rawInputs.len(); start += this.RawInputBatchSize)
    {
        local end = ::Math.min(rawInputs.len(), start + this.RawInputBatchSize);
        this._pushTask(
            tasks,
            "raw_input_batch",
            "raw_input_batch",
            (start / this.RawInputBatchSize).tostring(),
            { values = rawInputs, start = start, end = end }
        );
    }

    this._pushTask(tasks, "tactical_state_root", "tactical_state", "root");
    this._fieldTasks(
        tasks,
        "tactical_state_field",
        "tactical_state_field",
        _raw.TacticalState.m
    );
    this._pushTask(tasks, "turn_root", "turn", "root");
    this._fieldTasks(
        tasks,
        "turn_state_field",
        "turn_state_field",
        _raw.TurnSequenceBar.m
    );
    this._pushTask(tasks, "entity_manager_root", "entity_manager", "root");
    this._fieldTasks(
        tasks,
        "entity_manager_field",
        "entity_manager_field",
        _raw.EntityManager.m
    );
    this._pushTask(tasks, "constants", "constants", "root");
    this._pushTask(tasks, "player_legal_meta", "player_legal", "root");

    foreach (tile in _projection.state.tiles)
    {
        this._pushTask(
            tasks,
            "player_legal_tile",
            "player_legal_tile",
            tile.tile_id,
            tile
        );
    }
    foreach (actor in _projection.state.combatants)
    {
        this._pushTask(
            tasks,
            "player_legal_actor",
            "player_legal_actor",
            actor.actor_id,
            actor
        );
    }

    local memoryEntries = [];
    foreach (memoryKey, value in capture.getObservationMemory())
        memoryEntries.push({ name = memoryKey.tostring(), value = value });
    memoryEntries.sort(@(a, b) a.name <=> b.name);
    foreach (index, entry in memoryEntries)
    {
        this._pushTask(
            tasks,
            "observation_memory_entry",
            "observation_memory_entry",
            index.tostring(),
            { name = entry.name, value = entry.value }
        );
    }

    local actors = [];
    local groups = _raw.EntityManager.getAllInstances();
    foreach (group in groups)
    {
        foreach (actor in group)
        {
            if (actor == null || actor.isNull()) continue;
            actors.push(actor);
        }
    }
    actors.sort(@(a, b) a.getID() <=> b.getID());

    foreach (actor in actors)
    {
        local actorId = this._actorID(actor);
        this._pushTask(tasks, "actor_core", "actor", actorId, actor);
        this._pushTask(tasks, "actor_state", "actor_state", actorId, actor);
        this._pushTask(
            tasks,
            "actor_current_properties",
            "actor_current_properties",
            actorId,
            actor
        );
        this._pushTask(
            tasks,
            "actor_base_properties",
            "actor_base_properties",
            actorId,
            actor
        );
        this._pushTask(
            tasks,
            "actor_skills_container",
            "actor_skills_container",
            actorId,
            actor
        );
        this._pushTask(
            tasks,
            "actor_items_container",
            "actor_items_container",
            actorId,
            actor
        );
        this._pushTask(tasks, "actor_ai", "actor_ai", actorId, actor);

        local skills = [];
        try
        {
            foreach (skill in actor.getSkills().m.Skills)
            {
                if (skill == null || skill.isGarbage()) continue;
                skills.push(skill);
            }
        }
        catch (_error) {}
        skills.sort(@(a, b) a.getID() <=> b.getID());
        foreach (index, skill in skills)
        {
            this._pushTask(
                tasks,
                "actor_skill",
                "actor_skill",
                actorId + ":" + index.tostring(),
                { actor_id = actorId, skill = skill }
            );
        }

        local items = [];
        try
        {
            foreach (item in actor.getItems().getAllItems())
            {
                if (item == null || item == -1 || item.isGarbage()) continue;
                items.push(item);
            }
        }
        catch (_error) {}
        items.sort(@(a, b) a.getID() <=> b.getID());
        foreach (index, item in items)
        {
            this._pushTask(
                tasks,
                "actor_item",
                "actor_item",
                actorId + ":" + index.tostring(),
                { actor_id = actorId, item = item }
            );
        }
    }

    local size = ::Tactical.getMapSize();
    for (local x = 0; x < size.X; x = ++x)
    {
        for (local y = 0; y < size.Y; y = ++y)
        {
            if (!::Tactical.isValidTileSquare(x, y)) continue;
            local tile = ::Tactical.getTileSquare(x, y);
            this._pushTask(tasks, "tile", "tile", this._tileID(tile), tile);
        }
    }

    return {
        key = _raw.BattleSequence.tostring() + ":" + _raw.SourceGeneration.tostring(),
        raw = _raw,
        projection = _projection,
        active = _raw.ActiveActor,
        tasks = tasks,
        cursor = 0,
        expected_records = [],
        actor_count = actors.len(),
        tile_count = 0,
        initial_fingerprint = wire.canonicalHash(_raw.RawSourceFingerprintInputs)
    };
};

sandbox._runTask <- function(_job, _task)
{
    local payload = null;
    local kind = _task.kind;

    if (kind == "raw_root")
    {
        payload = {
            capture_contract_version = _job.raw.CaptureContractVersion,
            provenance = this._reflect(_job.raw.Provenance),
            battle_sequence = _job.raw.BattleSequence,
            source_generation = _job.raw.SourceGeneration,
            validation_context = this._reflect(_job.raw.ValidationContext),
            raw_source_fingerprint = _job.initial_fingerprint
        };
    }
    else if (kind == "raw_input_batch")
    {
        local values = [];
        for (local i = _task.extra.start; i < _task.extra.end; i = ++i)
            values.push(_task.extra.values[i]);
        payload = {
            start = _task.extra.start,
            end = _task.extra.end,
            values = values
        };
    }
    else if (kind == "tactical_state_root")
        payload = { runtime_type = typeof _job.raw.TacticalState };
    else if (kind == "tactical_state_field"
        || kind == "turn_state_field"
        || kind == "entity_manager_field")
    {
        payload = {
            field_name = _task.extra.field_name,
            value = this._reflect(_task.extra.state[_task.extra.field_key])
        };
    }
    else if (kind == "turn_root")
        payload = this._turnPayload(_job.raw);
    else if (kind == "entity_manager_root")
        payload = { runtime_type = typeof _job.raw.EntityManager };
    else if (kind == "constants")
        payload = this._constantsPayload(_job.active);
    else if (kind == "player_legal_meta")
        payload = this._playerLegalMeta(_job.projection);
    else if (kind == "player_legal_tile" || kind == "player_legal_actor")
        payload = _task.extra;
    else if (kind == "observation_memory_entry")
        payload = { memory_key = _task.extra.name, value = _task.extra.value };
    else if (kind == "actor_core")
        payload = this._actorCorePayload(_task.extra, _job.active);
    else if (kind == "actor_state")
        payload = this._reflect(_task.extra.m);
    else if (kind == "actor_current_properties")
        payload = this._reflect(_task.extra.getCurrentProperties());
    else if (kind == "actor_base_properties")
        payload = this._reflect(_task.extra.getBaseProperties());
    else if (kind == "actor_skills_container")
        payload = this._reflect(_task.extra.getSkills().m);
    else if (kind == "actor_items_container")
        payload = this._reflect(_task.extra.getItems().m);
    else if (kind == "actor_ai")
    {
        payload = null;
        try
        {
            local agent = _task.extra.getAIAgent();
            if (agent != null) payload = this._reflect(agent.m);
        }
        catch (_error) {}
    }
    else if (kind == "actor_skill")
    {
        payload = {
            actor_id = _task.extra.actor_id,
            skill = this._skillRecord(_task.extra.skill)
        };
    }
    else if (kind == "actor_item")
    {
        payload = {
            actor_id = _task.extra.actor_id,
            item = this._itemRecord(_task.extra.item)
        };
    }
    else if (kind == "tile")
    {
        payload = this._tilePayload(_task.extra);
        ++_job.tile_count;
    }
    else
        throw "unknown incremental combat sandbox task: " + kind;

    return this._emitRecord(
        _job.raw,
        _task.section,
        _task.key,
        payload
    );
};

sandbox._finishJob <- function(_job)
{
    local currentInputs = capture._fingerprintInputs(
        _job.raw.TacticalState,
        _job.raw.ActiveActor
    );
    local currentFingerprint = wire.canonicalHash(currentInputs);
    if (currentFingerprint != _job.initial_fingerprint)
    {
        ::logInfo(
            "[BB-Agent Combat Sandbox] discarded battle="
            + _job.raw.BattleSequence.tostring()
            + " generation=" + _job.raw.SourceGeneration.tostring()
            + " reason=source_changed"
        );
        this.ActiveJob = null;
        return;
    }

    _job.expected_records.push("manifest:root");
    _job.expected_records.sort();
    this._emitRecord(
        _job.raw,
        "manifest",
        "root",
        {
            information_scope = "omniscient_debug",
            scripts_revision = capture.SupportedScriptsRevision,
            ruleset_content_fingerprint = capture.RulesetContentFingerprint,
            companion_version = capture.State.Provenance.CompanionVersion,
            battle_sequence = _job.raw.BattleSequence,
            source_generation = _job.raw.SourceGeneration,
            active_actor_id = this._actorID(_job.raw.ActiveActor),
            actor_count = _job.actor_count,
            tile_count = _job.tile_count,
            expected_records = _job.expected_records,
            capture_mode = "incremental_real_time",
            batch_delay_ms = this.BatchDelayMs,
            batch_records_per_tick = this.BatchRecordsPerTick,
            consistency = {
                initial_raw_source_fingerprint = _job.initial_fingerprint,
                final_raw_source_fingerprint = currentFingerprint,
                matched = true
            },
            reflection = {
                max_depth = this.MaxReflectDepth,
                max_entries_per_container = this.MaxReflectEntries,
                nested_instances = "type marker only",
                unsupported_runtime_values = "type marker only"
            }
        }
    );

    this.LastSnapshotKey = _job.key;
    this.ActiveJob = null;
    ::logInfo(
        "[BB-Agent Combat Sandbox] emitted battle="
        + _job.raw.BattleSequence.tostring()
        + " generation=" + _job.raw.SourceGeneration.tostring()
        + " actors=" + _job.actor_count.tostring()
        + " tiles=" + _job.tile_count.tostring()
        + " records=" + _job.expected_records.len().tostring()
        + " mode=incremental_real_time"
    );
};

sandbox._runBatch <- function(_job)
{
    if (this.ActiveJob == null || this.ActiveJob.key != _job.key) return;
    try
    {
        local processed = 0;
        while (processed < this.BatchRecordsPerTick
            && _job.cursor < _job.tasks.len())
        {
            local task = _job.tasks[_job.cursor];
            ++_job.cursor;
            local recordId = this._runTask(_job, task);
            _job.expected_records.push(recordId);
            ++processed;
        }

        if (_job.cursor < _job.tasks.len())
        {
            this._scheduleBatch(_job);
            return;
        }
        this._finishJob(_job);
    }
    catch (error)
    {
        ::logError(
            "[BB-Agent Combat Sandbox] incremental_error=" + error.tostring()
        );
        this.ActiveJob = null;
    }
};

sandbox.capture = function(_raw, _projection)
{
    local key = _raw.BattleSequence.tostring() + ":" + _raw.SourceGeneration.tostring();
    if (this.LastSnapshotKey == key) return;
    if (this.ActiveJob != null)
    {
        if (this.ActiveJob.key == key) return;
        ::logInfo(
            "[BB-Agent Combat Sandbox] skipped reason=job_already_active active="
            + this.ActiveJob.key + " requested=" + key
        );
        return;
    }

    ::logInfo(
        "[BB-Agent Combat Sandbox] capture_attempt battle="
        + _raw.BattleSequence.tostring()
        + " generation=" + _raw.SourceGeneration.tostring()
        + " oracle_enabled=" + oracle.Enabled.tostring()
        + " mode=incremental_real_time"
    );
    if (!oracle.Enabled)
    {
        ::logInfo("[BB-Agent Combat Sandbox] skipped reason=oracle_disabled");
        return;
    }

    local job = this._buildJob(_raw, _projection);
    this.ActiveJob = job;
    ::logInfo(
        "[BB-Agent Combat Sandbox] started tasks=" + job.tasks.len().tostring()
        + " batch_records=" + this.BatchRecordsPerTick.tostring()
        + " delay_ms=" + this.BatchDelayMs.tostring()
    );
    this._scheduleBatch(job);
};

::logInfo("[BB-Agent Combat Sandbox] incremental_override_loaded mode=real_time");
