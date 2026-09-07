from __future__ import annotations

import argparse
import json
from pathlib import Path

from bb_agent.movement_sandbox import extract_latest_movement_sandbox


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract the latest BB-Agent movement sandbox snapshot from log.html."
    )
    parser.add_argument("--log", required=True, type=Path, help="Battle Brothers log.html")
    parser.add_argument("--out", required=True, type=Path, help="Output JSON fixture")
    return parser


def main() -> int:
    args = _parser().parse_args()
    snapshot = extract_latest_movement_sandbox(args.log)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(snapshot, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    payload = snapshot["payload"]
    state = payload.get("player_legal_state", {})
    movement = payload.get("movement_context", {})
    tiles = state.get("tiles", []) if isinstance(state, dict) else []
    actors = state.get("combatants", []) if isinstance(state, dict) else []
    print(f"Wrote movement sandbox snapshot: {args.out}")
    print(f"  battle={snapshot.get('battle_sequence')} generation={snapshot.get('source_generation')}")
    print(f"  active_tile={movement.get('active_tile_id')}")
    print(f"  tiles={len(tiles)} combatants={len(actors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
