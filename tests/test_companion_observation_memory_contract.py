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


def test_observation_memory_getter_returns_detached_entry_wrappers() -> None:
    text = _read(MEMORY)
    assert "capture.getObservationMemory = function()" in text
    assert "local snapshot = {};" in text
    assert "foreach (key, fact in this.State.ObservationMemory)" in text
    assert "snapshot[key] <- {" in text
    assert "Value = fact.Value" in text
    assert "ObservedRound = fact.ObservedRound" in text
    assert "ObservedDecision = fact.ObservedDecision" in text
    assert "return snapshot;" in text
    assert "return this.State.ObservationMemory" not in text
