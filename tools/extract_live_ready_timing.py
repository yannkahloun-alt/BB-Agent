from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bb_agent.live_ready_timing import summarize_latest_ready_timing  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract production DECISION_READY timing.")
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    try:
        summary = summarize_latest_ready_timing(args.log)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "PRODUCTION READY TIMING "
        f"battle={summary['battle_sequence']} generation={summary['source_generation']} "
        f"begin={summary['begin_time']} end={summary['end_time']} "
        f"span_seconds={summary['timestamp_span_seconds']} "
        f"same_timestamp_bucket={summary['same_timestamp_bucket']} "
        f"success={summary['success']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
