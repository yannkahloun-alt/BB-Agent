from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
MEMORY = ROOT / "companion_mod/scripts/bb_agent/observation_memory.nut"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_observation_memory_boundary_is_loaded_after_capture_substrate() -> None:
    preload = _read(PRELOAD)
    substrate = preload.index('::include("scripts/bb_agent/capture_substrate")')
    memory = preload.index('::include("scripts/bb_agent/observation_memory")')
    provenance = preload.index('::include("scripts/bb_agent/runtime_provenance")')
    assert substrate < memory < provenance


def test_observation_memory_accepts_only_json_like_player_legal_values() -> None:
    text = _read(MEMORY)
    assert "capture._isPlayerLegalMemoryValue <- function" in text
    for primitive in ('"null"', '"bool"', '"integer"', '"float"', '"string"'):
        assert primitive in text
    assert 'if (kind == "array")' in text
    assert 'if (kind == "table")' in text
    assert 'if (typeof key != "string") return false;' in text
    assert "return false;" in text
    assert "capture.rememberPlayerLegalFact = function" in text
    assert "this._isPlayerLegalMemoryValue(_value)" in text
    assert 'throw "observation-memory value must be player-legal data";' in text


def test_observation_memory_coordinates_match_canonical_observation_point() -> None:
    text = _read(MEMORY)
    assert 'typeof _round != "integer" || _round < 0' in text
    assert 'typeof _decision != "integer" || _decision < 0' in text
    assert 'throw "observation-memory round must be a non-negative integer";' in text
    assert 'throw "observation-memory decision must be a non-negative integer";' in text


def test_observation_memory_write_and_read_are_deep_copied() -> None:
    text = _read(MEMORY)
    assert "capture._copyPlayerLegalMemoryValue <- function" in text
    assert "copy.push(this._copyPlayerLegalMemoryValue(value));" in text
    assert "copy[key] <- this._copyPlayerLegalMemoryValue(value);" in text
    assert "Value = this._copyPlayerLegalMemoryValue(_value)" in text
    assert "capture.getObservationMemory = function()" in text
    assert "local snapshot = {};" in text
    assert "foreach (key, fact in this.State.ObservationMemory)" in text
    assert "snapshot[key] <- {" in text
    assert "Value = this._copyPlayerLegalMemoryValue(fact.Value)" in text
    assert "ObservedRound = fact.ObservedRound" in text
    assert "ObservedDecision = fact.ObservedDecision" in text
    assert "return snapshot;" in text
    assert "return this.State.ObservationMemory" not in text
