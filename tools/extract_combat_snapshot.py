from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bb_agent.combat_sandbox import (  # noqa: E402
    extract_latest_combat_sandbox,
    summarize_combat_sandbox_quality,
)
from bb_agent.oracle_validation import (  # noqa: E402
    summarize_ally_jump_probe,
    summarize_movement_validation,
)

_TEXT_RE = re.compile(r'<div class="text">(.*?)</div>', re.DOTALL)
_TAG_RE = re.compile(r"<.*?>")
_TAIL_BYTES = 262_144


def _sandbox_diagnostics(path: Path, *, tail_only: bool = False) -> list[str]:
    try:
        if tail_only:
            with path.open("rb") as handle:
                handle.seek(0, 2)
                size = handle.tell()
                handle.seek(max(0, size - _TAIL_BYTES))
                raw = handle.read().decode("utf-8", errors="replace")
        else:
            raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    result: list[str] = []
    for match in _TEXT_RE.finditer(raw):
        text = html.unescape(_TAG_RE.sub("", match.group(1))).strip()
        if "[BB-Agent Combat Sandbox]" in text:
            result.append(text)
    return result[-20:]


def _latest_sandbox_status(path: Path) -> tuple[str | None, bool, bool]:
    diagnostics = _sandbox_diagnostics(path, tail_only=True)
    if not diagnostics:
        return None, False, False
    latest = diagnostics[-1]
    complete = "[BB-Agent Combat Sandbox] complete " in latest
    terminal_failure = "[BB-Agent Combat Sandbox] cancelled " in latest
    return latest, complete, terminal_failure


def _print_incomplete(path: Path, problem: Exception | str) -> None:
    print(f"Combat sandbox is not complete: {problem}", file=sys.stderr)
    diagnostics = _sandbox_diagnostics(path, tail_only=True)
    if diagnostics:
        print("Latest sandbox diagnostics:", file=sys.stderr)
        for line in diagnostics:
            print(f"  {line}", file=sys.stderr)
    else:
        print("No combat sandbox diagnostics found in log.", file=sys.stderr)


def _format_movement_validation(validation: dict[str, Any]) -> str:
    return (
        "  movement_oracle="
        f"samples:{validation['sample_count']} "
        f"errors:{validation['error_count']} "
        f"legality_mismatches:{validation['legality_mismatch_count']} "
        f"reachability_mismatches:{validation['reachability_mismatch_count']} "
        f"comparable_costs:{validation['comparable_cost_sample_count']} "
        f"cost_mismatches:{validation['cost_mismatch_count']} "
        f"execution_fatigue_matches:{validation['execution_fatigue_match_count']} "
        f"path_fatigue_matches:{validation['path_fatigue_match_count']} "
        f"fatigue_neither:{validation['fatigue_semantics_neither_count']} "
        f"tile_count_mismatches:{validation['tile_count_mismatch_count']} "
        f"endpoint_mismatches:{validation['endpoint_mismatch_count']} "
        "native_paths_reconstructed:"
        f"{validation['native_path_reconstructed_count']} "
        "native_path_errors:"
        f"{validation['native_path_reconstruction_error_count']} "
        f"remembered_samples:{validation['remembered_sample_count']} "
        f"remembered_found:{validation['remembered_native_found_count']} "
        f"remembered_complete:{validation['remembered_native_complete_count']}"
    )


def _wait_for_completion(
    log_path: Path,
    *,
    wait_seconds: float,
    poll_seconds: float,
) -> bool:
    if wait_seconds <= 0:
        return True

    deadline = time.monotonic() + wait_seconds
    last_status: str | None = None
    while True:
        status, complete, terminal_failure = _latest_sandbox_status(log_path)
        if status is not None and status != last_status:
            print(status, flush=True)
            last_status = status
        if complete:
            return True
        if terminal_failure:
            _print_incomplete(log_path, status or "capture cancelled")
            return False
        if time.monotonic() >= deadline:
            _print_incomplete(log_path, "timed out waiting for completion marker")
            return False
        time.sleep(poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Extract the latest full BB-Agent combat sandbox from "
            "Battle Brothers log.html."
        )
    )
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=300.0,
        help="Poll lightweight log-tail diagnostics until capture completes.",
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

    if not _wait_for_completion(
        args.log,
        wait_seconds=args.wait_seconds,
        poll_seconds=args.poll_seconds,
    ):
        return 2

    try:
        snapshot = extract_latest_combat_sandbox(args.log)
    except ValueError as exc:
        _print_incomplete(args.log, exc)
        return 2

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
    quality = summarize_combat_sandbox_quality(snapshot)

    print(f"Wrote full combat sandbox: {args.out}")
    print(
        f"  battle={snapshot['battle_sequence']} "
        f"generation={snapshot['source_generation']}"
    )
    print(f"  records={len(records)}")
    print(f"  sections={dict(sorted(counts.items()))}")
    metrics = snapshot.get("extraction_metrics", {})
    build_span = metrics.get("player_legal_build_timestamp_span_seconds")
    print(
        "  player_legal_build="
        f"begin:{metrics.get('player_legal_build_begin_time')} "
        f"end:{metrics.get('player_legal_build_end_time')} "
        f"timestamp_span_seconds:{build_span} "
        f"same_timestamp_bucket:{metrics.get('player_legal_build_same_timestamp_bucket')}"
    )
    print(
        "  quality="
        f"capture_errors:{quality['capture_error_count']} "
        f"truncations:{quality['truncation_count']} "
        f"iteration_errors:{quality['iteration_error_count']} "
        f"semantic_errors:{quality['semantic_error_count']} "
        f"references:{quality['reference_summary_count']} "
        f"runtime_scaffolding:{quality['runtime_scaffolding_count']} "
        f"nested_shards:{quality['nested_shard_summary_count']}"
    )
    if "debug_probe:ally_jump" in records:
        comparison = summarize_ally_jump_probe(snapshot)
        print(
            "  ally_jump_oracle="
            f"candidate:{comparison['candidate']} "
            f"found:{comparison['found']} "
            f"complete:{comparison['complete']} "
            f"cost_agreement:{comparison['cost_agreement']} "
            f"direct_landing_rejected:{comparison['direct_landing_rejected']}"
        )
    if any(record_id.startswith("debug_movement_validation:") for record_id in records):
        validation = summarize_movement_validation(snapshot)
        print(_format_movement_validation(validation))
    if quality["issue_paths"]:
        print("  quality_issue_paths:")
        for path in quality["issue_paths"][:20]:
            print(f"    {path}")
        if len(quality["issue_paths"]) > 20:
            print(f"    ... {len(quality['issue_paths']) - 20} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
