local sandbox = ::BBAGENT_CombatSandbox;

// Oracle-first development captures omniscient script-readable fight state before
// rebuilding the PLAYER_LEGAL projection. Keep actual data fields, but do not pay
// one tactical update per executable/runtime-only method marker discovered while
// iterating class-like containers such as Tile.Properties.
sandbox._sandboxStateFieldKind <- function(_value)
{
    local kind = typeof _value;
    if (kind == "function"
        || kind == "nativeclosure"
        || kind == "class"
        || kind == "thread"
        || kind == "generator"
        || kind == "userdata"
        || kind == "weakref")
    {
        return kind;
    }
    return null;
};

sandbox._shardTopLevel = function(_ownerSection, _ownerKey, _container)
{
    local kind = typeof _container;
    local count = 0;
    local seen = 0;
    local truncated = false;
    local iterationError = null;
    local omittedRuntimeFields = [];

    if (kind == "array")
    {
        local limit = ::Math.min(_container.len(), this.MaxReflectEntries);
        for (local i = 0; i < limit; i = ++i)
        {
            ++seen;
            local omittedKind = this._sandboxStateFieldKind(_container[i]);
            if (omittedKind != null)
            {
                omittedRuntimeFields.push({
                    field_key_kind = "integer",
                    field_key_text = i.tostring(),
                    runtime_type = omittedKind
                });
                continue;
            }
            this._enqueueStateField(
                _ownerSection,
                _ownerKey,
                i,
                i,
                _container[i]
            );
            ++count;
        }
        truncated = _container.len() > limit;
    }
    else if (kind == "table" || kind == "instance")
    {
        try
        {
            foreach (key, value in _container)
            {
                if (seen >= this.MaxReflectEntries)
                {
                    truncated = true;
                    break;
                }
                local ordinal = seen;
                ++seen;
                local omittedKind = this._sandboxStateFieldKind(value);
                if (omittedKind != null)
                {
                    local meta = this._stateFieldKeyMeta(key);
                    omittedRuntimeFields.push({
                        field_key_kind = meta.field_key_kind,
                        field_key_text = meta.field_key_text,
                        runtime_type = omittedKind
                    });
                    continue;
                }
                this._enqueueStateField(
                    _ownerSection,
                    _ownerKey,
                    key,
                    ordinal,
                    value
                );
                ++count;
            }
        }
        catch (error)
        {
            iterationError = error.tostring();
        }
    }
    else if (kind != "null")
    {
        local omittedKind = this._sandboxStateFieldKind(_container);
        if (omittedKind != null)
        {
            omittedRuntimeFields.push({
                field_key_kind = "string",
                field_key_text = "value",
                runtime_type = omittedKind
            });
        }
        else
        {
            this._enqueueStateField(
                _ownerSection,
                _ownerKey,
                "value",
                0,
                _container
            );
            count = 1;
        }
        seen = 1;
    }

    local parent = {
        capture_mode = "top_level_field_shards",
        field_section = "state_field",
        owner_section = _ownerSection,
        owner_key = _ownerKey,
        runtime_type = kind,
        field_count = count,
        inspected_field_count = seen,
        omitted_runtime_field_count = omittedRuntimeFields.len(),
        omitted_runtime_fields = omittedRuntimeFields,
        truncated = truncated
    };
    if (iterationError != null) parent.iteration_error <- iterationError;
    if (kind == "array") parent.original_length <- _container.len();
    return parent;
};

local originalBegin = sandbox.begin;
sandbox.begin = function(_raw)
{
    originalBegin.acall([this, _raw]);
    if (this.State == null) return;

    local filtered = [];
    foreach (job in this.State.jobs)
        if (job.kind != "player_legal_build") filtered.push(job);
    this.State.jobs = filtered;
    if ("player_legal_projection" in this.State)
        delete this.State.player_legal_projection;
};

::logInfo(
    "[BB-Agent Combat Sandbox] oracle_first_loaded player_legal_deferred=true"
    + " runtime_scaffolding_sharded=false"
);
