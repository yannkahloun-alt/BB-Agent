"""Deterministic serialization primitives shared by later contract tickets."""

import hashlib
import json
import math
from collections.abc import Mapping, Sequence

type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | Sequence[JsonValue] | Mapping[str, JsonValue]


def _validate_json_value(value: JsonValue, path: str = "$") -> None:
    if value is None or isinstance(value, bool | int | str):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite number at {path}")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError(f"non-string object key at {path}")
            _validate_json_value(child, f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        for index, child in enumerate(value):
            _validate_json_value(child, f"{path}[{index}]")
        return
    raise TypeError(
        f"unsupported canonical JSON value at {path}: {type(value).__name__}"
    )


def canonical_json_bytes(value: JsonValue) -> bytes:
    """Serialize JSON data with stable keys and no environment-dependent whitespace."""
    _validate_json_value(value)
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_sha256(value: JsonValue) -> str:
    """Return the lowercase SHA-256 digest of canonical JSON bytes."""
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()
