"""Parse bounded production DECISION_READY timing markers from Battle Brothers logs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_MARKER_RE = re.compile(
    rb'<div class="time">([0-9]{2}:[0-9]{2}:[0-9]{2})</div>.*?'
    rb'<div class="text">\[BB-Agent Live Timing\] '
    rb"(ready_begin|ready_end) battle=([0-9]+) generation=([0-9]+)"
    rb"(?: success=(true|false))?(?: stage=([^< ]+))?</div>",
    re.DOTALL,
)
_STAGE_RE = re.compile(
    rb'<div class="time">([0-9]{2}:[0-9]{2}:[0-9]{2})</div>.*?'
    rb'<div class="text">\[BB-Agent Live Timing\] '
    rb"stage_(begin|end) stage=([^< ]+) battle=([0-9]+) "
    rb"generation=([0-9]+)</div>",
    re.DOTALL,
)


def _clock_seconds(value: str) -> int:
    hour, minute, second = (int(part) for part in value.split(":"))
    return hour * 3600 + minute * 60 + second


def summarize_latest_ready_timing(log_path: str | Path) -> dict[str, Any]:
    """Return the latest complete production READY timing pair."""

    data = Path(log_path).read_bytes()
    pairs: dict[tuple[int, int], dict[str, Any]] = {}
    order: list[tuple[int, int]] = []
    for match in _MARKER_RE.finditer(data):
        timestamp = match.group(1).decode("ascii")
        marker = match.group(2)
        key = (int(match.group(3)), int(match.group(4)))
        if key not in pairs:
            pairs[key] = {"battle_sequence": key[0], "source_generation": key[1]}
            order.append(key)
        pair = pairs[key]
        if marker == b"ready_begin":
            pair["begin_time"] = timestamp
        else:
            pair["end_time"] = timestamp
            pair["success"] = match.group(5) == b"true"
            stage = match.group(6)
            pair["failure_stage"] = stage.decode("ascii") if stage else None

    for key in reversed(order):
        pair = pairs[key]
        begin = pair.get("begin_time")
        end = pair.get("end_time")
        if begin is None or end is None:
            continue
        span = _clock_seconds(end) - _clock_seconds(begin)
        if span < 0:
            span += 24 * 60 * 60
        stage_starts: dict[str, str] = {}
        stage_spans: dict[str, int] = {}
        for stage_match in _STAGE_RE.finditer(data):
            stage_key = (int(stage_match.group(4)), int(stage_match.group(5)))
            if stage_key != key:
                continue
            stage_time = stage_match.group(1).decode("ascii")
            boundary = stage_match.group(2)
            stage = stage_match.group(3).decode("ascii")
            if boundary == b"begin":
                stage_starts[stage] = stage_time
            elif stage in stage_starts:
                stage_span = _clock_seconds(stage_time) - _clock_seconds(
                    stage_starts[stage]
                )
                if stage_span < 0:
                    stage_span += 24 * 60 * 60
                stage_spans[stage] = stage_span
        return {
            **pair,
            "timestamp_span_seconds": span,
            "same_timestamp_bucket": begin == end,
            "stage_span_seconds": stage_spans,
        }
    raise ValueError("no complete production READY timing pair found in log")
