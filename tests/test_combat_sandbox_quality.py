from bb_agent.combat_sandbox import summarize_combat_sandbox_quality


def _snapshot(records: dict[str, dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "bb-agent-combat-sandbox.v1",
        "battle_sequence": 1,
        "source_generation": 2,
        "records": records,
    }


def test_quality_summary_reports_clean_snapshot() -> None:
    summary = summarize_combat_sandbox_quality(
        _snapshot(
            {
                "raw:root": {
                    "section": "raw",
                    "key": "root",
                    "payload": {"ok": True},
                }
            }
        )
    )
    assert summary == {
        "capture_error_count": 0,
        "truncation_count": 0,
        "iteration_error_count": 0,
        "semantic_error_count": 0,
        "issue_paths": [],
    }


def test_quality_summary_finds_nested_errors_and_truncations() -> None:
    summary = summarize_combat_sandbox_quality(
        _snapshot(
            {
                "actor_state:actor:1": {
                    "section": "actor_state",
                    "key": "actor:1",
                    "payload": {
                        "capture_mode": "top_level_field_shards",
                        "truncated": True,
                        "iteration_error": "boom",
                    },
                },
                "state_field:7": {
                    "section": "state_field",
                    "key": "7",
                    "payload": {
                        "value": {
                            "__bb_type": "table",
                            "__bb_truncated": True,
                            "reason": "max_nodes",
                        }
                    },
                },
                "actor_ai:actor:1": {
                    "section": "actor_ai",
                    "key": "actor:1",
                    "payload": {"__capture_error": "unreadable"},
                },
            }
        )
    )
    assert summary["capture_error_count"] == 1
    assert summary["truncation_count"] == 2
    assert summary["iteration_error_count"] == 1
    assert summary["semantic_error_count"] == 0
    assert summary["issue_paths"] == sorted(summary["issue_paths"])
    assert any("actor_ai:actor:1" in path for path in summary["issue_paths"])
    assert any("state_field:7" in path for path in summary["issue_paths"])


def test_quality_summary_flags_missing_active_player_legal_actor() -> None:
    summary = summarize_combat_sandbox_quality(
        _snapshot(
            {
                "player_legal_meta:root": {
                    "section": "player_legal_meta",
                    "key": "root",
                    "payload": {
                        "information_profile": "player_legal",
                        "decision": {"active_actor_id": "actor:42"},
                    },
                }
            }
        )
    )

    assert summary["semantic_error_count"] == 1
    assert (
        "player_legal_meta:root.payload.decision.active_actor_id"
        in summary["issue_paths"]
    )
