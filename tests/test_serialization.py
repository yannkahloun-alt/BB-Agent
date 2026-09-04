import pytest

from bb_agent.serialization import canonical_json_bytes, canonical_sha256


def test_canonical_serialization_ignores_mapping_insertion_order() -> None:
    first = {"z": [3, 2, 1], "a": {"two": 2, "one": 1}}
    second = {"a": {"one": 1, "two": 2}, "z": [3, 2, 1]}

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert canonical_sha256(first) == canonical_sha256(second)
    assert canonical_json_bytes(first) == b'{"a":{"one":1,"two":2},"z":[3,2,1]}'


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_canonical_serialization_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="non-finite number"):
        canonical_json_bytes({"value": value})


def test_canonical_serialization_rejects_non_json_values() -> None:
    with pytest.raises(TypeError, match="unsupported canonical JSON value"):
        canonical_json_bytes({"unordered": {"a", "b"}})  # type: ignore[dict-item]
