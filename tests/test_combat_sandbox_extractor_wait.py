from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools/extract_combat_snapshot.py"
SPEC = importlib.util.spec_from_file_location(
    "extract_combat_snapshot_tool", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)


def _log(*messages: str) -> str:
    return "\n".join(f'<div class="text">{message}</div>' for message in messages)


def test_tail_status_reports_latest_progress_and_completion(tmp_path: Path) -> None:
    path = tmp_path / "log.html"
    path.write_text(
        _log(
            "noise",
            "[BB-Agent Combat Sandbox] staged battle=1 generation=0 initial_jobs=20",
            "[BB-Agent Combat Sandbox] progress battle=1 generation=0 "
            "cursor=64 jobs=900",
        ),
        encoding="utf-8",
    )

    status, complete, terminal = TOOL._latest_sandbox_status(path)
    assert status is not None and "cursor=64 jobs=900" in status
    assert complete is False
    assert terminal is False

    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n"
        + _log(
            "[BB-Agent Combat Sandbox] complete battle=1 generation=0 "
            "actors=20 tiles=400"
        ),
        encoding="utf-8",
    )
    status, complete, terminal = TOOL._latest_sandbox_status(path)
    assert status is not None and "complete battle=1" in status
    assert complete is True
    assert terminal is False


def test_tail_status_reports_terminal_cancellation(tmp_path: Path) -> None:
    path = tmp_path / "log.html"
    path.write_text(
        _log(
            "[BB-Agent Combat Sandbox] staged battle=1 generation=0 initial_jobs=20",
            "[BB-Agent Combat Sandbox] cancelled battle=1 generation=0 cursor=8 "
            "jobs=20 reason=generation_changed",
        ),
        encoding="utf-8",
    )

    status, complete, terminal = TOOL._latest_sandbox_status(path)
    assert status is not None and "reason=generation_changed" in status
    assert complete is False
    assert terminal is True


def test_waiter_uses_tail_status_without_full_snapshot_decode(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "log.html"
    path.write_text(
        _log(
            "[BB-Agent Combat Sandbox] complete battle=1 generation=0 actors=1 tiles=1"
        ),
        encoding="utf-8",
    )

    called = False

    def forbidden_decode(*_args: object, **_kwargs: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("waiter must not decode the full snapshot")

    monkeypatch.setattr(TOOL, "extract_latest_combat_sandbox", forbidden_decode)
    assert TOOL._wait_for_completion(path, wait_seconds=1.0, poll_seconds=0.01) is True
    assert called is False


def test_movement_summary_prints_native_prefix_path_counters() -> None:
    validation = {
        "sample_count": 2,
        "error_count": 1,
        "legality_mismatch_count": 0,
        "reachability_mismatch_count": 0,
        "comparable_cost_sample_count": 2,
        "cost_mismatch_count": 1,
        "execution_fatigue_match_count": 1,
        "path_fatigue_match_count": 1,
        "fatigue_semantics_neither_count": 0,
        "tile_count_mismatch_count": 1,
        "endpoint_mismatch_count": 1,
        "native_path_reconstructed_count": 1,
        "native_path_reconstruction_error_count": 1,
        "remembered_sample_count": 0,
        "remembered_native_found_count": 0,
        "remembered_native_complete_count": 0,
    }

    text = TOOL._format_movement_validation(validation)
    assert "native_paths_reconstructed:1" in text
    assert "native_path_errors:1" in text
