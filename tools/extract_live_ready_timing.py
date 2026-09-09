from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bb_agent.live_ready_timing import summarize_latest_ready_timing  # noqa: E402

_CAPTURE_ERROR_RE = re.compile(
    rb"\[BB-Agent Capture\] capture_error stage=([^ <]+) error=([^<]*?); advice invalidated"
)
_READINESS_RE = re.compile(rb"\[BB-Agent Capture\] readiness_blocked reason=([^< ]+)")


def _wait_for_summary(
    log: Path, wait_seconds: float, poll_seconds: float
) -> dict[str, object]:
    deadline = time.monotonic() + wait_seconds
    last_error: ValueError | None = None
    while True:
        try:
            return summarize_latest_ready_timing(log)
        except (FileNotFoundError, ValueError) as exc:
            last_error = ValueError(str(exc))
        if time.monotonic() >= deadline:
            assert last_error is not None
            raise last_error
        time.sleep(poll_seconds)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _decode_ascii(value: bytes | None) -> str | None:
    return value.decode("utf-8", errors="replace") if value is not None else None


def _incomplete_diagnostic(log: Path, error: str) -> dict[str, object]:
    try:
        data = log.read_bytes()
    except FileNotFoundError:
        return {
            "success": None,
            "diagnostic_status": "log_not_found",
            "diagnostic_error": error,
            "log_found": False,
        }

    begin_count = data.count(b"[BB-Agent Live Timing] ready_begin")
    end_count = data.count(b"[BB-Agent Live Timing] ready_end")
    capture_ready_count = data.count(b"[BB-Agent Capture] READY")
    export_error_count = data.count(b"[BB-Agent Capture] live_export_error")
    capture_errors = list(_CAPTURE_ERROR_RE.finditer(data))
    readiness_blocks = list(_READINESS_RE.finditer(data))
    timing_loaded = b"[BB-Agent Live Timing] loaded production_only=true" in data
    bb_agent_present = b"BB-Agent" in data

    latest_capture_error = capture_errors[-1] if capture_errors else None
    latest_readiness = readiness_blocks[-1] if readiness_blocks else None

    if not bb_agent_present:
        status = "no_bb_agent_log_entries"
    elif not timing_loaded:
        status = "timing_layer_not_loaded"
    elif begin_count == 0 and capture_errors:
        status = "capture_error_before_ready"
    elif begin_count == 0 and readiness_blocks:
        status = "readiness_blocked"
    elif begin_count == 0:
        status = "ready_never_began"
    elif end_count < begin_count:
        status = "ready_began_without_end"
    else:
        status = "no_complete_ready_timing_pair"

    return {
        "success": None,
        "diagnostic_status": status,
        "diagnostic_error": error,
        "log_found": True,
        "log_size_bytes": len(data),
        "bb_agent_log_present": bb_agent_present,
        "timing_layer_loaded": timing_loaded,
        "ready_begin_count": begin_count,
        "ready_end_count": end_count,
        "capture_ready_count": capture_ready_count,
        "capture_error_count": len(capture_errors),
        "latest_capture_error_stage": (
            _decode_ascii(latest_capture_error.group(1))
            if latest_capture_error is not None
            else None
        ),
        "latest_capture_error": (
            _decode_ascii(latest_capture_error.group(2))
            if latest_capture_error is not None
            else None
        ),
        "readiness_block_count": len(readiness_blocks),
        "latest_readiness_block_reason": (
            _decode_ascii(latest_readiness.group(1))
            if latest_readiness is not None
            else None
        ),
        "live_export_error_count": export_error_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract production DECISION_READY timing."
    )
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--wait-seconds", type=float, default=0.0)
    parser.add_argument("--poll-seconds", type=float, default=0.25)
    args = parser.parse_args()
    if args.wait_seconds < 0 or args.poll_seconds <= 0:
        parser.error("wait/poll durations must be positive")

    try:
        summary = _wait_for_summary(args.log, args.wait_seconds, args.poll_seconds)
    except ValueError as exc:
        diagnostic = _incomplete_diagnostic(args.log, str(exc))
        if args.out is not None:
            _write_json(args.out, diagnostic)
        print(str(exc), file=sys.stderr)
        return 2

    if args.out is not None:
        _write_json(args.out, summary)
    print(
        "PRODUCTION READY TIMING "
        f"battle={summary['battle_sequence']} "
        f"generation={summary['source_generation']} "
        f"begin={summary['begin_time']} end={summary['end_time']} "
        f"span_seconds={summary['timestamp_span_seconds']} "
        f"same_timestamp_bucket={summary['same_timestamp_bucket']} "
        f"success={summary['success']} "
        f"failure_stage={summary.get('failure_stage')}"
    )
    if summary["success"] is not True:
        print(
            "Production DECISION_READY export failed"
            f" at stage={summary.get('failure_stage')}",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
