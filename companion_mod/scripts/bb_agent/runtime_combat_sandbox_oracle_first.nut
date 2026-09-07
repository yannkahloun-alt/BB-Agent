local sandbox = ::BBAGENT_CombatSandbox;

// Oracle-first development captures omniscient script-readable fight state before
// rebuilding the PLAYER_LEGAL projection. Keep actual data fields, but do not pay
// one tactical update per executable/runtime-only method marker or scalar field.
// Scalars are grouped into one independently bounded pack per top-level container;
// nested/complex values remain independently sharded.
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

sandbox._sandboxScalarValue <- function(_value)
{
    local kind = typeof _value;
    if (kind == "null" || kind == "bool" || kind == "integer" || kind == "string")
        return { is_scalar = true, value = _value };
    if (kind == "float")
        return { is_scalar = true, value = this._floatValue(_value) };
    return { is_scalar = false, value = null };
};

sandbox._enqueueScalarPack <- function(_ownerSection, _ownerKey, _fields)
{
    if (_fields.len() == 0) return null;
    local key = this.State.scalar_pack_index.tostring();
    ++this.State.scalar_pack_index;
    this._enqueue(
        "state_scalar_pack",
        "state_scalar_pack",
        key,
        {
            owner_section = _ownerSection,
            owner_key = _ownerKey,
            fields = _fields
        }
    );
    return "state_scalar_pack:" + key;
};

sandbox._shardTopLevel = function(_ownerSection, _ownerKey, _container)
{
    local kind = typeof _container;
    local count = 0;
    local seen = 0;
    local truncated = false;
    local iterationError = null;
    local iterationUnavailable = null;
    local omittedRuntimeFields = [];
    local scalarFields = [];

    if (kind == "array")
    {
        local limit = ::Math.min(_container.len(), this.MaxReflectEntries);
        for (local i = 0; i < limit; i = ++i)
        {
            local ordinal = seen;
            ++seen;
            local value = _container[i];
            local omittedKind = this._sandboxStateFieldKind(value);
            if (omittedKind != null)
            {
                omittedRuntimeFields.push({
                    field_key_kind = "integer",
                    field_key_text = i.tostring(),
                    runtime_type = omittedKind
                });
                continue;
            }
            local scalar = this._sandboxScalarValue(value);
            if (scalar.is_scalar)
            {
                scalarFields.push({
                    field_key_kind = "integer",
                    field_key_text = i.tostring(),
                    ordinal = ordinal,
                    value = scalar.value
                });
                continue;
            }
            this._enqueueStateField(
                _ownerSection,
                _ownerKey,
                i,
                ordinal,
                value
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
                local meta = this._stateFieldKeyMeta(key);
                local omittedKind = this._sandboxStateFieldKind(value);
                if (omittedKind != null)
                {
                    omittedRuntimeFields.push({
                        field_key_kind = meta.field_key_kind,
                        field_key_text = meta.field_key_text,
                        runtime_type = omittedKind
                    });
                    continue;
                }
                local scalar = this._sandboxScalarValue(value);
                if (scalar.is_scalar)
                {
                    scalarFields.push({
                        field_key_kind = meta.field_key_kind,
                        field_key_text = meta.field_key_text,
                        ordinal = ordinal,
                        value = scalar.value
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
            local message = error.tostring();
            if (kind == "instance" && message == "_nexti failed")
                iterationUnavailable = "native_instance_not_enumerable";
            else
                iterationError = message;
        }
    }
    else if (kind != "null")
    {
        seen = 1;
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
            local scalar = this._sandboxScalarValue(_container);
            if (scalar.is_scalar)
            {
                scalarFields.push({
                    field_key_kind = "string",
                    field_key_text = "value",
                    ordinal = 0,
                    value = scalar.value
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
        }
    }

    local scalarPack = this._enqueueScalarPack(
        _ownerSection,
        _ownerKey,
        scalarFields
    );
    local parent = {
        capture_mode = "top_level_field_shards",
        field_section = "state_field",
        owner_section = _ownerSection,
        owner_key = _ownerKey,
        runtime_type = kind,
        field_count = count,
        scalar_field_count = scalarFields.len(),
        scalar_pack_record_id = scalarPack,
        inspected_field_count = seen,
        omitted_runtime_field_count = omittedRuntimeFields.len(),
        omitted_runtime_fields = omittedRuntimeFields,
        truncated = truncated
    };
    if (iterationError != null) parent.iteration_error <- iterationError;
    if (iterationUnavailable != null)
        parent.iteration_unavailable_reason <- iterationUnavailable;
    if (kind == "array") parent.original_length <- _container.len();
    return parent;
};

local originalProcessJob = sandbox._processJob;
sandbox._processJob = function(_job)
{
    if (_job.kind == "state_scalar_pack")
    {
        this._emitRecord(
            this.State.raw,
            _job.section,
            _job.key,
            _job.target
        );
        return;
    }
    return originalProcessJob.acall([this, _job]);
};

local originalBegin = sandbox.begin;
sandbox.begin = function(_raw)
{
    originalBegin.acall([this, _raw]);
    if (this.State == null) return;

    local filtered = [];
    local deferredPlayerLegal = null;
    foreach (job in this.State.jobs)
    {
        if (job.kind == "player_legal_build") deferredPlayerLegal = job;
        else filtered.push(job);
    }
    if (deferredPlayerLegal != null) filtered.push(deferredPlayerLegal);
    this.State.jobs = filtered;
    if (!("scalar_pack_index" in this.State))
        this.State.scalar_pack_index <- 0;
};

::logInfo(
    "[BB-Agent Combat Sandbox] oracle_first_loaded player_legal_deferred=last"
    + " runtime_scaffolding_sharded=false scalar_pack_records=true"
);
