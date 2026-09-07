import pytest

from bb_agent.oracle_validation import (
    summarize_ally_jump_probe,
    summarize_movement_validation,
)


def _snapshot(payload: dict[str, object]) -> dict[str, object]:
    return {
        "records": {
            "debug_probe:ally_jump": {
                "section": "debug_probe",
                "key": "ally_jump",
                "payload": payload,
            }
        }
    }


def test_ally_jump_probe_reports_constituent_step_agreement() -> None:
    summary = summarize_ally_jump_probe(
        _snapshot(
            {
                "candidate": True,
                "found": True,
                "complete": True,
                "from_tile_id": "tile:12:18",
                "ally_tile_id": "tile:12:19",
                "landing_tile_id": "tile:12:20",
                "native_tiles": 2,
                "native_ap": 4,
                "native_fatigue": 6,
                "two_step_ap": 4,
                "two_step_fatigue": 6,
                "landing_step_ap": 2,
                "landing_step_fatigue": 2,
            }
        )
    )

    assert summary["cost_agreement"] is True
    assert summary["direct_landing_rejected"] is True
    assert summary["native_tiles"] == 2


def test_ally_jump_probe_preserves_no_candidate_without_inventing_comparison() -> None:
    summary = summarize_ally_jump_probe(_snapshot({"candidate": False}))
    assert summary["candidate"] is False
    assert summary["cost_agreement"] is None
    assert summary["direct_landing_rejected"] is None


def test_ally_jump_probe_rejects_missing_record() -> None:
    with pytest.raises(ValueError, match="record is missing"):
        summarize_ally_jump_probe({"records": {}})


def test_movement_validation_aggregates_agreement_and_mismatches() -> None:
    snapshot = {
        "records": {
            "debug_movement_validation:0": {
                "payload": {
                    "role": "nearest_reachable",
                    "model_reachable": True,
                    "native_complete": True,
                    "legality_agreement": True,
                    "reachability_agreement": True,
                    "cost_agreement": True,
                    "native_matches_execution_fatigue": True,
                    "native_matches_path_fatigue": True,
                }
            },
            "debug_movement_validation:1": {
                "payload": {
                    "role": "zoc_exit",
                    "model_reachable": True,
                    "native_complete": True,
                    "legality_agreement": True,
                    "reachability_agreement": True,
                    "cost_agreement": False,
                    "native_matches_execution_fatigue": False,
                    "native_matches_path_fatigue": True,
                }
            },
            "debug_movement_validation:2": {
                "payload": {
                    "role": "highest_cost_reachable",
                    "model_reachable": True,
                    "native_complete": True,
                    "legality_agreement": True,
                    "reachability_agreement": True,
                    "cost_agreement": False,
                    "native_matches_execution_fatigue": False,
                    "native_matches_path_fatigue": False,
                }
            },
            "debug_movement_validation:3": {
                "payload": {
                    "role": "model_legal_resource_unreachable",
                    "model_reachable": False,
                    "native_complete": True,
                    "legality_agreement": False,
                    "reachability_agreement": False,
                    "cost_agreement": False,
                }
            },
        }
    }

    summary = summarize_movement_validation(snapshot)
    assert summary["sample_count"] == 4
    assert summary["roles"] == [
        "nearest_reachable",
        "zoc_exit",
        "highest_cost_reachable",
        "model_legal_resource_unreachable",
    ]
    assert summary["legality_mismatch_count"] == 1
    assert summary["reachability_mismatch_count"] == 1
    assert summary["comparable_cost_sample_count"] == 3
    assert summary["cost_mismatch_count"] == 2
    assert summary["execution_fatigue_match_count"] == 1
    assert summary["path_fatigue_match_count"] == 2
    assert summary["fatigue_semantics_neither_count"] == 1
    assert summary["error_count"] == 0


def test_movement_validation_reports_sample_errors() -> None:
    summary = summarize_movement_validation(
        {
            "records": {
                "debug_movement_validation:plan_error": {
                    "payload": {"role": "plan_error", "error": "boom"}
                }
            }
        }
    )
    assert summary["sample_count"] == 1
    assert summary["error_count"] == 1
    assert summary["errors"] == ["boom"]
