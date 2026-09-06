local wire = ::BBAGENT_Wire <- {
    EnvelopeVersion = "bb-agent-live-envelope.v1",
    CaptureContractVersion = "bb-agent-live-capture.v1",
    FramePrefix = "BBAGENT1",
    Hex = "0123456789abcdef",
    Base64Url = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_",
    Mask32 = 4294967295,

    KernelIdentity = {
        action_affordance = "issue-4.amended-by-13.contingent-reactions-19.identity-40",
        decision_trace_contract = "issue-7.amended-by-13",
        evaluation_config = "m1-evaluation-profile.v2",
        evaluation_contract = "issue-5.amended-by-13",
        evaluation_profile_fingerprint = "2e0ff58c4c57a80dc37eb86da5d49ef573057abd73eb158801f5c600c0c6ffcb",
        evaluator_model = "risk-evaluator.v1",
        information_policy = "issue-2.amended-by-13",
        m1_spec = "issues-1-through-13.freeze-1",
        mechanics_manifest = "bb-agent-mechanics-manifest.v1",
        mechanics_manifest_fingerprint = "9f692baf73145ead5be654c5044c16cf70c8d5d7dad83ece9525bae252bb67e8",
        outcome_model = "ordinary-attack.v1",
        tactical_state = "issue-3.amended-by-13.contingent-reactions-19.identity-40",
        trace_schema = "bb-agent-decision-trace.v1",
        uncertainty_contract = "issue-6.amended-by-13",
        unit_value_policy_fingerprint = "170f540b3f76cb01ca88048dcb13cb66f57f96b2ea464c6a122292309179c2b7",
        unit_value_policy_version = "m1-common-preservation.v1"
    },

    function _u32(_value)
    {
        return _value & this.Mask32;
    },

    function _add32(_a, _b)
    {
        return this._u32(this._u32(_a) + this._u32(_b));
    },

    function _rotr(_value, _bits)
    {
        local value = this._u32(_value);
        return this._u32((value >> _bits) | this._u32(value << (32 - _bits)));
    },

    function _hexNibble(_value)
    {
        return this.Hex.slice(_value, _value + 1);
    },

    function _hexByte(_value)
    {
        return this._hexNibble((_value >> 4) & 15) + this._hexNibble(_value & 15);
    },

    function _jsonEscape(_value)
    {
        local out = "\"";
        foreach (byte in _value)
        {
            if (byte == 34) out += "\\\"";
            else if (byte == 92) out += "\\\\";
            else if (byte == 8) out += "\\b";
            else if (byte == 12) out += "\\f";
            else if (byte == 10) out += "\\n";
            else if (byte == 13) out += "\\r";
            else if (byte == 9) out += "\\t";
            else if (byte < 32) out += "\\u00" + this._hexByte(byte);
            else out += byte.tochar();
        }
        return out + "\"";
    },

    function canonicalJson(_value)
    {
        local kind = typeof _value;
        if (kind == "null") return "null";
        if (kind == "bool") return _value ? "true" : "false";
        if (kind == "integer") return _value.tostring();
        if (kind == "float") throw "canonical live JSON does not accept floats";
        if (kind == "string") return this._jsonEscape(_value);
        if (kind == "array")
        {
            local parts = [];
            foreach (child in _value) parts.push(this.canonicalJson(child));
            return "[" + parts.join(",") + "]";
        }
        if (kind == "table")
        {
            local keys = [];
            foreach (key, _child in _value)
            {
                if (typeof key != "string") throw "canonical JSON object keys must be strings";
                keys.push(key);
            }
            keys.sort();
            local parts = [];
            foreach (key in keys)
                parts.push(this._jsonEscape(key) + ":" + this.canonicalJson(_value[key]));
            return "{" + parts.join(",") + "}";
        }
        throw "unsupported canonical live JSON type: " + kind;
    },

    function sha256(_message)
    {
        local h = [
            1779033703, -1150833019, 1013904242, -1521486534,
            1359893119, -1694144372, 528734635, 1541459225
        ];
        local k = [
            1116352408, 1899447441, -1245643825, -373957723,
            961987163, 1508970993, -1841331548, -1424204075,
            -670586216, 310598401, 607225278, 1426881987,
            1925078388, -2132889090, -1680079193, -1046744716,
            -459576895, -272742522, 264347078, 604807628,
            770255983, 1249150122, 1555081692, 1996064986,
            -1740746414, -1473132947, -1341970488, -1084653625,
            -958395405, -710438585, 113926993, 338241895,
            666307205, 773529912, 1294757372, 1396182291,
            1695183700, 1986661051, -2117940946, -1838011259,
            -1564481375, -1474664885, -1035236496, -949202525,
            -778901479, -694614492, -200395387, 275423344,
            430227734, 506948616, 659060556, 883997877,
            958139571, 1322822218, 1537002063, 1747873779,
            1955562222, 2024104815, -2067236844, -1933114872,
            -1866530822, -1538233109, -1090935817, -965641998
        ];
        local bytes = [];
        foreach (byte in _message) bytes.push(byte);
        local bitLength = bytes.len() * 8;
        bytes.push(128);
        while ((bytes.len() % 64) != 56) bytes.push(0);
        bytes.push(0); bytes.push(0); bytes.push(0); bytes.push(0);
        bytes.push((bitLength >> 24) & 255);
        bytes.push((bitLength >> 16) & 255);
        bytes.push((bitLength >> 8) & 255);
        bytes.push(bitLength & 255);

        for (local offset = 0; offset < bytes.len(); offset += 64)
        {
            local w = array(64, 0);
            for (local i = 0; i < 16; i = ++i)
            {
                local p = offset + i * 4;
                w[i] = this._u32(
                    (bytes[p] << 24) | (bytes[p + 1] << 16)
                    | (bytes[p + 2] << 8) | bytes[p + 3]
                );
            }
            for (local i = 16; i < 64; i = ++i)
            {
                local s0 = this._rotr(w[i - 15], 7) ^ this._rotr(w[i - 15], 18) ^ (this._u32(w[i - 15]) >> 3);
                local s1 = this._rotr(w[i - 2], 17) ^ this._rotr(w[i - 2], 19) ^ (this._u32(w[i - 2]) >> 10);
                w[i] = this._add32(this._add32(w[i - 16], s0), this._add32(w[i - 7], s1));
            }

            local a = this._u32(h[0]);
            local b = this._u32(h[1]);
            local c = this._u32(h[2]);
            local d = this._u32(h[3]);
            local e = this._u32(h[4]);
            local f = this._u32(h[5]);
            local g = this._u32(h[6]);
            local hh = this._u32(h[7]);

            for (local i = 0; i < 64; i = ++i)
            {
                local s1 = this._rotr(e, 6) ^ this._rotr(e, 11) ^ this._rotr(e, 25);
                local ch = this._u32((e & f) ^ ((~e) & g));
                local t1 = this._add32(
                    this._add32(this._add32(this._add32(hh, s1), ch), k[i]),
                    w[i]
                );
                local s0 = this._rotr(a, 2) ^ this._rotr(a, 13) ^ this._rotr(a, 22);
                local maj = this._u32((a & b) ^ (a & c) ^ (b & c));
                local t2 = this._add32(s0, maj);
                hh = g;
                g = f;
                f = e;
                e = this._add32(d, t1);
                d = c;
                c = b;
                b = a;
                a = this._add32(t1, t2);
            }

            h[0] = this._add32(h[0], a);
            h[1] = this._add32(h[1], b);
            h[2] = this._add32(h[2], c);
            h[3] = this._add32(h[3], d);
            h[4] = this._add32(h[4], e);
            h[5] = this._add32(h[5], f);
            h[6] = this._add32(h[6], g);
            h[7] = this._add32(h[7], hh);
        }

        local out = "";
        foreach (value in h)
        {
            local u = this._u32(value);
            for (local shift = 28; shift >= 0; shift -= 4)
                out += this._hexNibble((u >> shift) & 15);
        }
        return out;
    },

    function canonicalHash(_value)
    {
        return this.sha256(this.canonicalJson(_value));
    },

    function base64Url(_raw)
    {
        local out = "";
        for (local i = 0; i < _raw.len(); i += 3)
        {
            local a = _raw[i];
            local hasB = i + 1 < _raw.len();
            local hasC = i + 2 < _raw.len();
            local b = hasB ? _raw[i + 1] : 0;
            local c = hasC ? _raw[i + 2] : 0;
            out += this.Base64Url.slice((a >> 2) & 63, ((a >> 2) & 63) + 1);
            local v1 = ((a & 3) << 4) | ((b >> 4) & 15);
            out += this.Base64Url.slice(v1, v1 + 1);
            if (hasB)
            {
                local v2 = ((b & 15) << 2) | ((c >> 6) & 3);
                out += this.Base64Url.slice(v2, v2 + 1);
            }
            if (hasC)
            {
                local v3 = c & 63;
                out += this.Base64Url.slice(v3, v3 + 1);
            }
        }
        return out;
    },

    function encodeFrame(_record)
    {
        local raw = this.canonicalJson(_record);
        return this.FramePrefix + "|" + raw.len() + "|" + this.sha256(raw)
            + "|" + this.base64Url(raw);
    },

    function unknownValue()
    {
        return {
            basis = [], candidates = [], confidence = null, distribution = [],
            knowledge_class = "UNKNOWN", maximum = null, minimum = null,
            observed_at = null, representation = "UNKNOWN", value = null
        };
    },

    function exactObserved(_value)
    {
        return {
            basis = [], candidates = [], confidence = null, distribution = [],
            knowledge_class = "EXACT_OBSERVED", maximum = null, minimum = null,
            observed_at = null, representation = "EXACT", value = _value
        };
    },

    function observed(_value)
    {
        return {
            basis = [], candidates = [], confidence = null, distribution = [],
            knowledge_class = "OBSERVED", maximum = null, minimum = null,
            observed_at = null, representation = "EXACT", value = _value
        };
    },

    function remembered(_value, _round, _decision)
    {
        return {
            basis = [], candidates = [], confidence = null, distribution = [],
            knowledge_class = "REMEMBERED", maximum = null, minimum = null,
            observed_at = { round = _round, decision = _decision },
            representation = "EXACT", value = _value
        };
    },

    function exactSet(_values)
    {
        local values = clone _values;
        values.sort();
        return {
            basis = [], candidates = values, confidence = null, distribution = [],
            knowledge_class = "EXACT_OBSERVED", maximum = null, minimum = null,
            observed_at = null, representation = "SET", value = null
        };
    },

    function resolvedCost(_value, _authority = "GAME_PLAYER_AFFORDANCE")
    {
        return { authority = _authority, stage = "SOURCE_RESOLVED", value = _value };
    },

    function resolvedPreview(_value)
    {
        return { authority = "PLAYER_UI", stage = "PREVIEW_RESOLVED", value = _value };
    }
};
