from pathlib import Path

import pytest

from bb_agent.live_ready_timing import summarize_latest_ready_timing

ROOT = Path(__file__).resolve().parents[1]
PRELOAD = ROOT / "companion_mod/scripts/!mods_preload/mod_bb_agent_capture.nut"
TIMING = ROOT / "companion_mod/scripts/bb_agent/runtime_live_ready_timing.nut"
INSTALLER = ROOT / "tools/install_live_production.ps1"


def _log(*rows: tuple[str, str]) -> bytes:
    return "\n".join(
        f'<div class="time">{timestamp}</div><div class="text">{text}</div>'
        for timestamp, text in rows
    ).encode()


def test_timing_wrapper_loads_after_failure_latch_before_tactical_hook() -> None:
    preload = PRELOAD.read_text(encoding="utf-8")
    assert 'Version = "0.2.37"' in preload
    latch = preload.index("runtime_ready_failure_latch")
    timing = preload.index("runtime_live_ready_timing")
    hook = preload.index("hooks/tactical_state")
    assert latch < timing < hook


def test_timing_wrapper_is_production_only_and_rethrows() -> None:
    text = TIMING.read_text(encoding="utf-8")
    assert "if (oracle.Enabled)" in text
    assert "originalEmitReady.acall" in text
    assert "ready_begin" in text
    assert "ready_end" in text
    assert "success=true" in text
    assert "success=false" in text
    assert "throw error;" in text
    for forbidden in ("payload", "getAllInstances", "findPath(", "getCostForPath("):
        assert forbidden not in text


def test_timing_parser_reports_latest_complete_pair(tmp_path: Path) -> None:
    path = tmp_path / "log.html"
    path.write_bytes(
        _log(
            ("10:00:00", "[BB-Agent Live Timing] ready_begin battle=1 generation=2"),
            (
                "10:00:03",
                "[BB-Agent Live Timing] ready_end battle=1 generation=2 success=true",
            ),
            ("10:05:00", "[BB-Agent Live Timing] ready_begin battle=1 generation=3"),
            (
                "10:05:01",
                "[BB-Agent Live Timing] ready_end battle=1 generation=3 success=false",
            ),
        )
    )
    assert summarize_latest_ready_timing(path) == {
        "battle_sequence": 1,
        "source_generation": 3,
        "begin_time": "10:05:00",
        "end_time": "10:05:01",
        "success": False,
        "timestamp_span_seconds": 1,
        "same_timestamp_bucket": False,
    }


def test_timing_parser_handles_midnight_rollover(tmp_path: Path) -> None:
    path = tmp_path / "log.html"
    path.write_bytes(
        _log(
            ("23:59:59", "[BB-Agent Live Timing] ready_begin battle=4 generation=8"),
            (
                "00:00:01",
                "[BB-Agent Live Timing] ready_end battle=4 generation=8 success=true",
            ),
        )
    )
    assert summarize_latest_ready_timing(path)["timestamp_span_seconds"] == 2


def test_timing_parser_requires_complete_pair(tmp_path: Path) -> None:
    path = tmp_path / "log.html"
    path.write_bytes(
        _log(("10:00:00", "[BB-Agent Live Timing] ready_begin battle=1 generation=2"))
    )
    with pytest.raises(ValueError, match="no complete production READY timing pair"):
        summarize_latest_ready_timing(path)


def test_production_installer_excludes_debug_overlay() -> None:
    text = INSTALLER.read_text(encoding="utf-8")
    assert 'Version = "0\\.2\\.37"' in text
    assert "runtime_live_ready_timing" in text
    assert "exactly one BB-Agent production zip" in text
    assert "zz_bb_agent_debug_oracle.zip" not in text
    assert "Copy-Item (Join-Path $RepoRoot 'companion_mod\\debug_oracle" not in text
