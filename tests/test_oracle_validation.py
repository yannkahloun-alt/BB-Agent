import pytest

from bb_agent.oracle_validation import summarize_ally_jump_probe


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
