from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bb_agent.live_ready_timing import summarize_latest_ready_timing  # noqa: E402


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
        diagnostic: dict[str, object] = {
            "success": None,
            "diagnostic_status": "no_complete_ready_timing_pair",
            "diagnostic_error": str(exc),
        }
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
