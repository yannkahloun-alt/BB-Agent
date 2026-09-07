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

from bb_agent.combat_sandbox import extract_latest_combat_sandbox


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract the latest full BB-Agent combat sandbox from Battle Brothers log.html."
    )
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=0.0,
        help="Poll until a complete manifest-backed snapshot exists.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=0.25,
        help="Polling interval used with --wait-seconds.",
    )
    args = parser.parse_args()

    if args.wait_seconds < 0 or args.poll_seconds <= 0:
        parser.error("wait/poll durations must be positive")

    deadline = time.monotonic() + args.wait_seconds
    last_error: ValueError | None = None
    while True:
        try:
            snapshot = extract_latest_combat_sandbox(args.log)
            break
        except ValueError as exc:
            last_error = exc
            if time.monotonic() >= deadline:
                print(f"Combat sandbox is not complete: {exc}", file=sys.stderr)
                return 2
            time.sleep(args.poll_seconds)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(snapshot, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    records = snapshot["records"]
    counts: dict[str, int] = {}
    for record_id in records:
        section = record_id.split(":", 1)[0]
        counts[section] = counts.get(section, 0) + 1
    print(f"Wrote full combat sandbox: {args.out}")
    print(
        f"  battle={snapshot['battle_sequence']} "
        f"generation={snapshot['source_generation']}"
    )
    print(f"  records={len(records)}")
    print(f"  sections={dict(sorted(counts.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
