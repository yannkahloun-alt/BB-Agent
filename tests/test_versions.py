from bb_agent.versions import CURRENT_VERSIONS


def test_version_registry_references_frozen_contracts() -> None:
    versions = CURRENT_VERSIONS.as_mapping()

    assert versions["m1_spec"] == "issues-1-through-13.freeze-1"
    assert versions["information_policy"] == "issue-2.amended-by-13"
    assert (
        versions["action_affordance"]
        == "issue-4.amended-by-13.contingent-reactions-19.identity-40"
    )
    assert (
        versions["tactical_state"]
        == "issue-3.amended-by-13.contingent-reactions-19.identity-40"
    )
    assert set(versions) == {
        "m1_spec",
        "information_policy",
        "tactical_state",
        "action_affordance",
        "evaluation",
        "uncertainty",
        "decision_trace",
        "mechanics_manifest",
        "outcome_model",
        "evaluation_config",
        "fixture",
    }


def test_version_registry_is_read_only() -> None:
    versions = CURRENT_VERSIONS.as_mapping()

    try:
        versions["m1_spec"] = "changed"  # type: ignore[index]
    except TypeError:
        pass
    else:
        raise AssertionError("version registry unexpectedly allowed mutation")
