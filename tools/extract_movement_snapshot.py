from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bb_agent.combat_sandbox import extract_latest_combat_sandbox


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract the latest full BB-Agent combat sandbox from log.html."
    )
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    snapshot = extract_latest_combat_sandbox(args.log)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(snapshot, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    records = snapshot.get("records", {})
    sections: dict[str, int] = {}
    for record_id in records:
        section = record_id.split(":", 1)[0]
        sections[section] = sections.get(section, 0) + 1
    print(f"Wrote full combat sandbox: {args.out}")
    print(
        f"  battle={snapshot.get('battle_sequence')} "
        f"generation={snapshot.get('source_generation')}"
    )
    print(f"  records={len(records)} sections={dict(sorted(sections.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
