from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bb_agent.movement_sandbox import extract_latest_movement_sandbox

_TEXT_RE = re.compile(r'<div class="text">(.*?)</div>', re.DOTALL)
_TAG_RE = re.compile(r"<.*?>")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract the latest BB-Agent movement sandbox snapshot from log.html."
    )
    parser.add_argument("--log", required=True, type=Path, help="Battle Brothers log.html")
    parser.add_argument("--out", required=True, type=Path, help="Output JSON fixture")
    return parser


def _relevant_log_lines(path: Path) -> list[str]:
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    result: list[str] = []
    for match in _TEXT_RE.finditer(raw):
        text = html.unescape(_TAG_RE.sub("", match.group(1))).strip()
        if (
            "[BB-Agent Sandbox]" in text
            or "DEBUG_ORACLE explicitly enabled" in text
            or "[BB-Agent Capture]" in text
            or "BB-Agent Capture 0.2.23" in text
        ):
            result.append(text)
    return result[-40:]


def main() -> int:
    args = _parser().parse_args()
    try:
        snapshot = extract_latest_movement_sandbox(args.log)
    except ValueError as exc:
        print(f"Movement sandbox extraction failed: {exc}", file=sys.stderr)
        lines = _relevant_log_lines(args.log)
        if lines:
            print("Relevant Battle Brothers log entries:", file=sys.stderr)
            for line in lines:
                print(f"  {line}", file=sys.stderr)
        else:
            print("No BB-Agent sandbox/oracle/capture diagnostics found in log.", file=sys.stderr)
        return 2

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
    print(
        f"  battle={snapshot.get('battle_sequence')} "
        f"generation={snapshot.get('source_generation')}"
    )
    print(f"  active_tile={movement.get('active_tile_id')}")
    print(f"  tiles={len(tiles)} combatants={len(actors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
