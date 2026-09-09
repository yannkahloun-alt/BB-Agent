from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
COMPAT = ROOT / "companion_mod/scripts/bb_agent/runtime_join_compat.nut"


def test_join_compat_loads_before_tactical_hook() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    live_export = preload.index('::include("scripts/bb_agent/live_export")')
    compat = preload.index('::include("scripts/bb_agent/runtime_join_compat")')
    hook = preload.index('::include("scripts/bb_agent/hooks/tactical_state")')
    assert live_export < compat < hook


def test_join_compat_uses_supported_manual_iteration() -> None:
    text = COMPAT.read_text(encoding="utf-8")
    assert "function joinStrings(_values, _separator)" in text
    assert "for (local i = 0; i < _values.len(); i = ++i)" in text
    assert "if (i != 0) out += _separator;" in text
    assert "out += _values[i];" in text
    assert ".join(" not in text


def test_join_compat_overrides_all_active_join_paths() -> None:
    text = COMPAT.read_text(encoding="utf-8")
    for required in (
        "capture._arrayToken = function",
        "capture._actorToken = function",
        "capture._sourceSignature = function",
        "capture._sanitizeDiagnosticError = function",
        "wire.canonicalJson = function",
        "liveExport._sanitizeExportError = function",
    ):
        assert required in text

    assert 'compat.joinStrings(parts, ",")' in text
    assert 'compat.joinStrings(tokens, ",")' in text
    assert 'compat.joinStrings(_inputs, "\\x1f")' in text
    assert 'compat.joinStrings(split(errorText, "\\r\\n\\t"), " ")' in text


def test_live_base64_uses_bounded_chunks_without_changing_alphabet() -> None:
    text = COMPAT.read_text(encoding="utf-8")
    start = text.index("wire.base64Url = function")
    end = text.index("liveExport._sanitizeExportError", start)
    encoder = text[start:end]
    for required in (
        "for (local i = 0; i < _raw.len(); i += 3)",
        "this.Base64Url.slice(v0, v0 + 1)",
        "this.Base64Url.slice(v1, v1 + 1)",
        "this.Base64Url.slice(v2, v2 + 1)",
        "this.Base64Url.slice(v3, v3 + 1)",
        "if (chunk.len() >= 4096)",
        "return compat.joinBalanced(chunks);",
    ):
        assert required in encoder
    assert 'chunk += "="' not in encoder
    assert "while (level.len() > 1)" in text
    assert "level[i] + level[i + 1]" in text


def test_join_compat_preserves_safety_boundary() -> None:
    text = COMPAT.read_text(encoding="utf-8")
    for forbidden in (
        "Math.rand(",
        "::Math.rand(",
        ".payForAction(",
        ".equip(",
        ".unequip(",
        ".swap(",
        ".use(",
        ".wait(",
        ".endTurn(",
        "getNavigator().travel(",
        "DEBUG_GROUND_TRUTH",
        "DEBUG_ORACLE",
        "omniscient_debug",
    ):
        assert forbidden not in text
