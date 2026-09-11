import pytest

from bb_agent.oracle_validation import (
    reconstruct_native_prefix_path,
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
                    "tile_count_agreement": True,
                    "endpoint_agreement": True,
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
                    "tile_count_agreement": False,
                    "endpoint_agreement": True,
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
                    "tile_count_agreement": True,
                    "endpoint_agreement": False,
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
            "debug_movement_validation:remembered_0": {
                "payload": {
                    "role": "remembered_nearest",
                    "player_legal_visibility": "REMEMBERED",
                    "native_found": True,
                    "native_complete": True,
                }
            },
        }
    }

    summary = summarize_movement_validation(snapshot)
    assert summary["sample_count"] == 5
    assert summary["roles"] == [
        "nearest_reachable",
        "zoc_exit",
        "highest_cost_reachable",
        "model_legal_resource_unreachable",
        "remembered_nearest",
    ]
    assert summary["legality_mismatch_count"] == 1
    assert summary["reachability_mismatch_count"] == 1
    assert summary["comparable_cost_sample_count"] == 3
    assert summary["cost_mismatch_count"] == 2
    assert summary["execution_fatigue_match_count"] == 1
    assert summary["path_fatigue_match_count"] == 2
    assert summary["fatigue_semantics_neither_count"] == 1
    assert summary["tile_count_mismatch_count"] == 1
    assert summary["endpoint_mismatch_count"] == 1
    assert summary["native_path_reconstructed_count"] == 0
    assert summary["native_path_reconstruction_error_count"] == 0
    assert summary["remembered_sample_count"] == 1
    assert summary["remembered_roles"] == ["remembered_nearest"]
    assert summary["remembered_native_found_count"] == 1
    assert summary["remembered_native_complete_count"] == 1
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
    assert summary["remembered_sample_count"] == 0
    assert summary["error_count"] == 1
    assert summary["errors"] == ["boom"]


def test_reconstructs_captured_native_path_from_cost_prefix_anchors() -> None:
    prefixes = [
        {"tiles": 0, "end_tile_id": "tile:12:18", "anchor_tile_ids": []},
        {
            "tiles": 1,
            "end_tile_id": "tile:11:17",
            "anchor_tile_ids": ["tile:11:17"],
        },
        {
            "tiles": 2,
            "end_tile_id": "tile:10:17",
            "anchor_tile_ids": ["tile:11:17", "tile:10:17"],
        },
        {
            "tiles": 3,
            "end_tile_id": "tile:10:16",
            "anchor_tile_ids": [
                "tile:11:17",
                "tile:10:17",
                "tile:10:16",
            ],
        },
        {
            "tiles": 4,
            "end_tile_id": "tile:10:15",
            "anchor_tile_ids": [
                "tile:11:17",
                "tile:10:17",
                "tile:10:16",
                "tile:10:15",
            ],
        },
    ]
    neighbors = {
        "tile:12:18": ["tile:11:17"],
        "tile:11:17": ["tile:10:17"],
        "tile:10:17": ["tile:10:16"],
        "tile:10:16": ["tile:10:15"],
        "tile:10:15": [],
    }

    assert reconstruct_native_prefix_path(
        origin_tile_id="tile:12:18",
        destination_tile_id="tile:10:15",
        prefixes=prefixes,
        neighbor_ids=neighbors,
    ) == ["tile:11:17", "tile:10:17", "tile:10:16", "tile:10:15"]


@pytest.mark.parametrize(
    ("prefixes", "match"),
    [
        (
            [{"tiles": 1, "end_tile_id": "tile:c", "anchor_tile_ids": ["tile:c"]}],
            "canonical path gap",
        ),
        (
            [
                {
                    "tiles": 1,
                    "end_tile_id": "tile:b",
                    "anchor_tile_ids": ["tile:b"],
                },
                {
                    "tiles": 2,
                    "end_tile_id": "tile:a",
                    "anchor_tile_ids": ["tile:a"],
                },
            ],
            "revisited an earlier path endpoint",
        ),
    ],
)
def test_native_prefix_reconstruction_rejects_gaps_and_loops(
    prefixes: list[dict[str, object]], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        reconstruct_native_prefix_path(
            origin_tile_id="tile:a",
            destination_tile_id="tile:c",
            prefixes=prefixes,
            neighbor_ids={
                "tile:a": ["tile:b"],
                "tile:b": ["tile:c"],
                "tile:c": [],
            },
        )
