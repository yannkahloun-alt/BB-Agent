"""Offline validation helpers for bounded DEBUG_ORACLE sandbox records."""

from __future__ import annotations

from typing import Any


def summarize_ally_jump_probe(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Compare the sandbox ally-jump native sample with modeled step totals."""

    records = snapshot.get("records")
    if not isinstance(records, dict):
        raise ValueError("combat sandbox records are invalid")

    record = records.get("debug_probe:ally_jump")
    if not isinstance(record, dict):
        raise ValueError("ally-jump debug probe record is missing")
    payload = record.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("ally-jump debug probe payload is invalid")

    candidate = payload.get("candidate") is True
    result: dict[str, Any] = {
        "candidate": candidate,
        "found": payload.get("found") if candidate else None,
        "complete": payload.get("complete") if candidate else None,
        "from_tile_id": payload.get("from_tile_id"),
        "ally_tile_id": payload.get("ally_tile_id"),
        "landing_tile_id": payload.get("landing_tile_id"),
        "native_tiles": payload.get("native_tiles"),
        "native_ap": payload.get("native_ap"),
        "native_fatigue": payload.get("native_fatigue"),
        "modeled_ap": payload.get("two_step_ap"),
        "modeled_fatigue": payload.get("two_step_fatigue"),
        "direct_landing_ap": payload.get("landing_step_ap"),
        "direct_landing_fatigue": payload.get("landing_step_fatigue"),
        "error": payload.get("error") or payload.get("probe_setup_error"),
    }

    if not candidate:
        result["cost_agreement"] = None
        result["direct_landing_rejected"] = None
        return result

    native_ap = result["native_ap"]
    native_fatigue = result["native_fatigue"]
    modeled_ap = result["modeled_ap"]
    modeled_fatigue = result["modeled_fatigue"]
    result["cost_agreement"] = (
        native_ap is not None
        and native_fatigue is not None
        and native_ap == modeled_ap
        and native_fatigue == modeled_fatigue
    )

    direct_ap = result["direct_landing_ap"]
    direct_fatigue = result["direct_landing_fatigue"]
    result["direct_landing_rejected"] = (
        native_ap is not None
        and native_fatigue is not None
        and direct_ap is not None
        and direct_fatigue is not None
        and (native_ap != direct_ap or native_fatigue != direct_fatigue)
    )
    return result


def summarize_movement_validation(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Aggregate staged DEBUG_ORACLE/native movement comparison records."""

    records = snapshot.get("records")
    if not isinstance(records, dict):
        raise ValueError("combat sandbox records are invalid")

    samples: list[dict[str, Any]] = []
    for record_id, record in sorted(records.items()):
        if not record_id.startswith("debug_movement_validation:"):
            continue
        if not isinstance(record, dict):
            raise ValueError("movement validation record is invalid")
        payload = record.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("movement validation payload is invalid")
        samples.append(payload)

    roles = [sample.get("role") for sample in samples]
    errors = [
        sample.get("error") for sample in samples if sample.get("error") is not None
    ]
    legality_mismatches = sum(
        1 for sample in samples if sample.get("legality_agreement") is False
    )
    reachability_mismatches = sum(
        1 for sample in samples if sample.get("reachability_agreement") is False
    )
    comparable_cost_samples = sum(
        1
        for sample in samples
        if sample.get("model_reachable") is True
        and sample.get("native_complete") is True
    )
    cost_mismatches = sum(
        1
        for sample in samples
        if sample.get("model_reachable") is True
        and sample.get("native_complete") is True
        and sample.get("cost_agreement") is False
    )
    execution_fatigue_matches = sum(
        1
        for sample in samples
        if sample.get("native_matches_execution_fatigue") is True
    )
    path_fatigue_matches = sum(
        1
        for sample in samples
        if sample.get("native_matches_path_fatigue") is True
    )
    fatigue_semantics_neither = sum(
        1
        for sample in samples
        if sample.get("model_reachable") is True
        and sample.get("native_complete") is True
        and sample.get("native_matches_execution_fatigue") is False
        and sample.get("native_matches_path_fatigue") is False
    )

    return {
        "sample_count": len(samples),
        "roles": roles,
        "error_count": len(errors),
        "errors": errors,
        "legality_mismatch_count": legality_mismatches,
        "reachability_mismatch_count": reachability_mismatches,
        "comparable_cost_sample_count": comparable_cost_samples,
        "cost_mismatch_count": cost_mismatches,
        "execution_fatigue_match_count": execution_fatigue_matches,
        "path_fatigue_match_count": path_fatigue_matches,
        "fatigue_semantics_neither_count": fatigue_semantics_neither,
    }
