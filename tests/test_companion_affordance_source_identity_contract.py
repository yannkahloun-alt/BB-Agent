from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
IDENTITY = ROOT / "companion_mod/scripts/bb_agent/affordance_source_identity.nut"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_affordance_source_identity_is_loaded_after_capture_substrate() -> None:
    preload = _read(PRELOAD)
    substrate = preload.index('::include("scripts/bb_agent/capture_substrate")')
    identity = preload.index('::include("scripts/bb_agent/affordance_source_identity")')
    memory = preload.index('::include("scripts/bb_agent/observation_memory")')
    assert substrate < identity < memory


def test_active_item_slot_topology_is_part_of_raw_source_identity() -> None:
    text = _read(IDENTITY)
    required = (
        "_active.getItems().m.Items",
        "foreach (slotIndex, slotItems",
        "foreach (position, item",
        'slotPrefix + ":empty"',
        'slotPrefix + ":blocked"',
        'slotPrefix + ":item=" + item.getID()',
        'itemPrefix + ":condition=" + item.getCondition()',
        "itemPrefix + \":m\"",
        "item.m",
        "originalFingerprintInputs.acall([this, _state, _active])",
        "this._activeItemSlotTopologyTokens(_active)",
        "ret.sort();",
    )
    for token in required:
        assert token in text, token


def test_tile_effect_primitive_state_is_part_of_single_map_identity_pass() -> None:
    text = _read(IDENTITY)
    required = (
        "capture._mapTokens = function()",
        "::Tactical.getMapSize()",
        "::Tactical.isValidTileSquare(x, y)",
        "::Tactical.getTileSquare(x, y)",
        '"map=" + x + ":" + y',
        "tile.Properties.Effect == null",
        '"tile_effect=" + x + ":" + y',
        "tile.Properties.Effect",
        "this._primitiveStateTokens(",
    )
    for token in required:
        assert token in text, token
    assert "capture._tileEffectTokens" not in text


def test_affordance_source_identity_extension_is_read_only() -> None:
    text = _read(IDENTITY)
    forbidden = (
        ".equip(",
        ".swap(",
        ".payForAction(",
        "setActionPoints(",
        "Math.rand(",
        "getNavigator().travel(",
        ".use(",
        ".wait(",
        ".endTurn(",
        "Properties.Effect =",
    )
    for token in forbidden:
        assert token not in text, token
