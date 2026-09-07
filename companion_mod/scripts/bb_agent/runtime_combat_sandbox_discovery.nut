local sandbox = ::BBAGENT_CombatSandbox;
local capture = ::BBAGENT_Capture;
local oracle = ::BBAGENT_DebugOracle;

// Building the forensic work queue must be bounded too. The base sandbox already
// emits one logical record per tactical update; this override also discovers raw
// inputs, actors, skills, items and map squares through cursor jobs so begin()
// never walks the full roster or tactical map in one callback.

sandbox._enqueueActorDiscoveryRecords <- function(_actor)
{
    local actorId = this._actorID(_actor);
    ++this.State.actor_count;

    this._enqueue("actor_core", "actor_core", actorId, _actor);
    this._enqueue("actor_state", "actor_state", actorId, _actor);
    this._enqueue("actor_properties", "actor_properties", actorId, _actor);
    this._enqueue(
        "actor_skills_container",
        "actor_skills_container",
        actorId,
        _actor
    );
    this._enqueue(
        "actor_items_container",
        "actor_items_container",
        actorId,
        _actor
    );
    this._enqueue("actor_ai", "actor_ai", actorId, _actor);

    local skills = null;
    try { skills = _actor.getSkills().m.Skills; } catch (_error) {}
    if (skills != null)
    {
        this._enqueue(
            "discover_actor_skill",
            null,
            null,
            null,
            {
                actor_id = actorId,
                skills = skills,
                skill_index = 0
            },
            false
        );
    }

    local items = null;
    try { items = _actor.getItems().getAllItems(); } catch (_error) {}
    if (items != null)
    {
        this._enqueue(
            "discover_actor_item",
            null,
            null,
            null,
            {
                actor_id = actorId,
                items = items,
                item_index = 0
            },
            false
        );
    }
};

sandbox._processDiscovery <- function(_job)
{
    if (_job.kind == "discover_raw_input")
    {
        local index = _job.extra;
        local inputs = this.State.raw.RawSourceFingerprintInputs;
        if (index >= inputs.len()) return true;

        this._enqueue(
            "raw_fingerprint_input",
            "raw_fingerprint_input",
            index.tostring(),
            inputs[index],
            index
        );
        this._enqueue(
            "discover_raw_input",
            null,
            null,
            null,
            index + 1,
            false
        );
        return true;
    }

    if (_job.kind == "discover_actor")
    {
        if (this.State.actor_groups == null)
            this.State.actor_groups = this.State.raw.EntityManager.getAllInstances();

        local groupIndex = _job.extra.group_index;
        local actorIndex = _job.extra.actor_index;
        local groups = this.State.actor_groups;
        if (groupIndex >= groups.len()) return true;

        local group = groups[groupIndex];
        if (actorIndex >= group.len())
        {
            this._enqueue(
                "discover_actor",
                null,
                null,
                null,
                { group_index = groupIndex + 1, actor_index = 0 },
                false
            );
            return true;
        }

        local actor = group[actorIndex];
        if (actor != null && !actor.isNull())
            this._enqueueActorDiscoveryRecords(actor);

        this._enqueue(
            "discover_actor",
            null,
            null,
            null,
            { group_index = groupIndex, actor_index = actorIndex + 1 },
            false
        );
        return true;
    }

    if (_job.kind == "discover_actor_skill")
    {
        local skillIndex = _job.extra.skill_index;
        local skills = _job.extra.skills;
        if (skillIndex >= skills.len()) return true;

        local skill = skills[skillIndex];
        if (skill != null && !skill.isGarbage())
        {
            this._enqueue(
                "actor_skill",
                "actor_skill",
                _job.extra.actor_id + ":" + skillIndex.tostring(),
                skill,
                _job.extra.actor_id
            );
        }
        this._enqueue(
            "discover_actor_skill",
            null,
            null,
            null,
            {
                actor_id = _job.extra.actor_id,
                skills = skills,
                skill_index = skillIndex + 1
            },
            false
        );
        return true;
    }

    if (_job.kind == "discover_actor_item")
    {
        local itemIndex = _job.extra.item_index;
        local items = _job.extra.items;
        if (itemIndex >= items.len()) return true;

        local item = items[itemIndex];
        if (item != null && item != -1 && !item.isGarbage())
        {
            this._enqueue(
                "actor_item",
                "actor_item",
                _job.extra.actor_id + ":" + itemIndex.tostring(),
                item,
                _job.extra.actor_id
            );
        }
        this._enqueue(
            "discover_actor_item",
            null,
            null,
            null,
            {
                actor_id = _job.extra.actor_id,
                items = items,
                item_index = itemIndex + 1
            },
            false
        );
        return true;
    }

    if (_job.kind == "discover_tile")
    {
        if (this.State.map_size == null)
            this.State.map_size = ::Tactical.getMapSize();

        local x = _job.extra.x;
        local y = _job.extra.y;
        local size = this.State.map_size;
        if (x >= size.X) return true;

        if (::Tactical.isValidTileSquare(x, y))
        {
            local tile = ::Tactical.getTileSquare(x, y);
            this._enqueue("tile", "tile", this._tileID(tile), tile);
            ++this.State.tile_count;
        }

        local nextX = x;
        local nextY = y + 1;
        if (nextY >= size.Y)
        {
            nextX = x + 1;
            nextY = 0;
        }
        this._enqueue(
            "discover_tile",
            null,
            null,
            null,
            { x = nextX, y = nextY },
            false
        );
        return true;
    }

    return false;
};

local originalProcessJob = sandbox._processJob;
sandbox._processJob = function(_job)
{
    if (_job.kind == "discover_raw_input"
        || _job.kind == "discover_actor"
        || _job.kind == "discover_actor_skill"
        || _job.kind == "discover_actor_item"
        || _job.kind == "discover_tile")
    {
        try
        {
            this._processDiscovery(_job);
        }
        catch (error)
        {
            ::logError(
                "[BB-Agent Combat Sandbox] discovery_error kind=" + _job.kind
                + " error=" + error.tostring()
            );
            this.cancel("discovery_error");
        }
        return;
    }
    return originalProcessJob.acall([this, _job]);
};

sandbox.begin = function(_raw)
{
    if (!oracle.Enabled || _raw == null) return;
    local key = _raw.BattleSequence.tostring() + ":" + _raw.SourceGeneration.tostring();
    if (this.LastSnapshotKey == key) return;
    if (this.State != null
        && this.State.battle_sequence == _raw.BattleSequence
        && this.State.source_generation == _raw.SourceGeneration)
    {
        return;
    }
    if (this.State != null) this.cancel("superseded_generation");

    this.State = {
        raw = _raw,
        battle_sequence = _raw.BattleSequence,
        source_generation = _raw.SourceGeneration,
        jobs = [],
        cursor = 0,
        expected_records = [],
        expected_shards = [],
        actor_count = 0,
        tile_count = 0,
        finalizing = false,
        player_legal_projection = null,
        actor_groups = null,
        map_size = null
    };

    this._enqueue("player_legal_build", null, null, null, null, false);
    this._enqueue("raw_meta", "raw", "root");
    this._enqueue("discover_raw_input", null, null, null, 0, false);
    this._enqueue("tactical_state", "tactical_state", "root");
    this._enqueue("turn", "turn", "root");
    this._enqueue("entity_manager", "entity_manager", "root");
    this._enqueue("tactical_global", "tactical_global", "root");
    this._enqueue("navigator", "navigator", "root");
    this._enqueue("navigator_settings", "navigator_settings", "active_player");
    this._enqueue("constant", "constant", "movement");
    this._enqueue("constant", "constant", "direction");
    this._enqueue("constant", "constant", "tactical");
    this._enqueue("constant", "constant", "combat");
    this._enqueue("constant", "constant", "items");
    this._enqueue("constant", "constant", "skill_type");
    this._enqueue("constant", "constant", "item_slot");
    this._enqueue("constant", "constant", "body_part");
    this._enqueue("constant", "constant", "morale_state");
    this._enqueue(
        "discover_actor",
        null,
        null,
        null,
        { group_index = 0, actor_index = 0 },
        false
    );
    this._enqueue(
        "discover_tile",
        null,
        null,
        null,
        { x = 0, y = 0 },
        false
    );

    ::logInfo(
        "[BB-Agent Combat Sandbox] staged battle=" + _raw.BattleSequence.tostring()
        + " generation=" + _raw.SourceGeneration.tostring()
        + " initial_jobs=" + this.State.jobs.len().tostring()
        + " discovery=incremental"
    );
};

::logInfo("[BB-Agent Combat Sandbox] discovery_loaded incremental=true");
