"""Run the documented M1 reference-machine decision latency benchmark."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from bb_agent.evaluator import DEFAULT_EVALUATION_PROFILE, DEFAULT_UNIT_VALUE_POLICY
from bb_agent.fixtures import FixtureEnvelope, load_fixture
from bb_agent.mechanics import load_builtin_mechanics
from bb_agent.results import ResultStatus
from bb_agent.trace import run_decision_trace
from bb_agent.versions import CURRENT_VERSIONS

BENCHMARK_VERSION = "m1-reference-latency.v1"
DEFAULT_PASSES = 7
DEFAULT_WARMUP_PASSES = 1
MEDIAN_TARGET_MS = 250.0
P95_TARGET_MS = 1000.0
HARD_MAX_MS = 3000.0


def _percentile(values: list[int], quantile: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _cpu_model() -> str:
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.processor() or "unknown"


def _load_corpus(root: Path) -> tuple[FixtureEnvelope, ...]:
    fixtures = []
    for directory in (
        root / "tests" / "fixtures" / "ticket_24",
        root / "tests" / "fixtures" / "ticket_25",
    ):
        for path in sorted(directory.glob("*.json")):
            loaded = load_fixture(path)
            if loaded.status is not ResultStatus.SUCCESS or loaded.value is None:
                raise RuntimeError(f"fixture load failed: {path}: {loaded.problems}")
            fixtures.append(loaded.value)
    return tuple(fixtures)


def run_benchmark(*, passes: int, warmup_passes: int) -> dict[str, object]:
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("M1 reference benchmark requires CPython 3.12")
    if passes <= 0 or warmup_passes < 0:
        raise ValueError("passes must be positive and warmup passes nonnegative")

    root = Path(__file__).resolve().parents[1]
    fixtures = _load_corpus(root)
    if len(fixtures) != 54:
        raise RuntimeError(f"expected 54 promoted M1 fixtures, got {len(fixtures)}")

    authority_result = load_builtin_mechanics()
    if authority_result.status is not ResultStatus.SUCCESS or authority_result.value is None:
        raise RuntimeError(f"mechanics load failed: {authority_result.problems}")
    authority = authority_result.value

    for _ in range(warmup_passes):
        for fixture in fixtures:
            run_decision_trace(authority, fixture)

    wall_ns: list[int] = []
    stage_ns: list[int] = []
    branch_counts: list[int] = []
    sample_counts: list[int] = []
    candidate_counts: list[int] = []
    status_counts: Counter[str] = Counter()
    slowest: tuple[int, str, dict[str, object]] | None = None

    for _ in range(passes):
        for fixture in fixtures:
            started = time.perf_counter_ns()
            trace = run_decision_trace(authority, fixture)
            elapsed = time.perf_counter_ns() - started
            wall_ns.append(elapsed)

            status = str(trace.generation["decision_status"])
            status_counts[status] += 1
            timings = trace.performance.get("stage_timings_ns", {})
            if not isinstance(timings, dict):
                raise RuntimeError("trace performance timings are malformed")
            stage_total = sum(
                value
                for value in timings.values()
                if isinstance(value, int) and not isinstance(value, bool)
            )
            stage_ns.append(stage_total)

            counters = trace.performance.get("counters", {})
            if not isinstance(counters, dict):
                raise RuntimeError("trace performance counters are malformed")
            branch_counts.append(int(counters.get("outcome_branch_count", 0)))
            sample_counts.append(int(counters.get("sample_count", 0)))
            candidate_counts.append(int(counters.get("legal_candidate_count", 0)))

            if slowest is None or elapsed > slowest[0]:
                slowest = (
                    elapsed,
                    fixture.metadata.fixture_id,
                    {
                        "status": status,
                        "stage_timings_ns": dict(sorted(timings.items())),
                        "counters": dict(sorted(counters.items())),
                    },
                )

    assert slowest is not None
    wall_ms = {
        "median": statistics.median(wall_ns) / 1e6,
        "p95": _percentile(wall_ns, 0.95) / 1e6,
        "max": max(wall_ns) / 1e6,
    }
    passes_targets = (
        wall_ms["median"] <= MEDIAN_TARGET_MS
        and wall_ms["p95"] <= P95_TARGET_MS
        and wall_ms["max"] <= HARD_MAX_MS
    )

    return {
        "benchmark_version": BENCHMARK_VERSION,
        "revision": _git(root, "rev-parse", "HEAD"),
        "tree": _git(root, "rev-parse", "HEAD^{tree}"),
        "workflow_pin": _git(root, "-C", ".agent-workflow", "rev-parse", "HEAD"),
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "kernel": platform.release(),
        "machine": platform.machine(),
        "cpu_model": _cpu_model(),
        "logical_cpu_count": os.cpu_count(),
        "process_state": (
            f"warmed: {warmup_passes} complete 54-fixture pass(es) before measurement"
        ),
        "fixture_set": "ticket_24 + ticket_25 promoted M1 corpus",
        "fixture_count": len(fixtures),
        "measurement_passes": passes,
        "decision_samples": len(wall_ns),
        "contract_versions": dict(CURRENT_VERSIONS.as_mapping()),
        "evaluation_profile_version": DEFAULT_EVALUATION_PROFILE.version,
        "evaluation_profile_fingerprint": DEFAULT_EVALUATION_PROFILE.fingerprint,
        "unit_value_policy_version": DEFAULT_UNIT_VALUE_POLICY.version,
        "unit_value_policy_fingerprint": DEFAULT_UNIT_VALUE_POLICY.fingerprint,
        "mechanics_manifest_version": CURRENT_VERSIONS.mechanics_manifest,
        "mechanics_manifest_fingerprint": authority.manifest.fingerprint,
        "outcome_model_version": CURRENT_VERSIONS.outcome_model,
        "sampling": {
            "max_sample_count": max(sample_counts),
            "total_sample_count_across_measured_decisions": sum(sample_counts),
            "max_exact_branch_count": max(branch_counts),
        },
        "candidate_counts": {
            "min": min(candidate_counts),
            "median": statistics.median(candidate_counts),
            "max": max(candidate_counts),
        },
        "status_counts_across_measured_decisions": dict(sorted(status_counts.items())),
        "wall_clock_ms": wall_ms,
        "evaluator_stage_ms": {
            "median": statistics.median(stage_ns) / 1e6,
            "p95": _percentile(stage_ns, 0.95) / 1e6,
            "max": max(stage_ns) / 1e6,
        },
        "slowest_fixture": {
            "fixture_id": slowest[1],
            "wall_clock_ms": slowest[0] / 1e6,
            **slowest[2],
        },
        "targets_ms": {
            "median": MEDIAN_TARGET_MS,
            "p95": P95_TARGET_MS,
            "hard_max": HARD_MAX_MS,
        },
        "passes_targets": passes_targets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--passes", type=int, default=DEFAULT_PASSES)
    parser.add_argument("--warmup-passes", type=int, default=DEFAULT_WARMUP_PASSES)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = run_benchmark(passes=args.passes, warmup_passes=args.warmup_passes)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if bool(result["passes_targets"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
