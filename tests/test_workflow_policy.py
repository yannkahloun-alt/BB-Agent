"""Regression coverage for the shared-workflow policy specialization."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_TAG = "v1.1.3"
WORKFLOW_COMMIT = "ff0647d3dc205a47734d569ae5247ee4ba9109e9"
OLD_WORKFLOW_COMMIT = "4171010e1a17643876036b3dfd463b2e3a615c5f"


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_workflow_pin_is_synchronized_across_git_policy_and_verifier() -> None:
    agents = _read("AGENTS.md")
    dependency = _read("docs/AGENT_WORKFLOW_DEPENDENCY.md")
    verifier = _read("tools/verify_workflow_dependency.py")
    recorded = subprocess.run(
        ["git", "rev-parse", "HEAD:.agent-workflow"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert WORKFLOW_TAG in agents
    assert WORKFLOW_TAG in dependency
    assert WORKFLOW_COMMIT in agents
    assert WORKFLOW_COMMIT in dependency
    assert f'EXPECTED_COMMIT = "{WORKFLOW_COMMIT}"' in verifier
    assert recorded == WORKFLOW_COMMIT
    assert OLD_WORKFLOW_COMMIT not in agents
    assert OLD_WORKFLOW_COMMIT not in dependency
    assert OLD_WORKFLOW_COMMIT not in verifier


def test_ci_owned_validation_policy_does_not_restore_routine_local_gates() -> None:
    agents = _read("AGENTS.md")
    testing = _read("docs/TESTING.md").replace("\n", " ")

    assert "does **not** run CI-equivalent" in testing
    assert (
        "Local automated validation is reserved for a check genuinely unavailable"
        in testing
    )
    assert "manual reference or explicit debugging" in testing
    assert "Routine autonomous work does not duplicate" in agents
    assert "## Local commands equivalent to CI" not in testing


def test_current_ci_contract_replaces_issue_14_bootstrap_wording() -> None:
    readme = _read("README.md")
    agents = _read("AGENTS.md")
    testing = _read("docs/TESTING.md")

    assert "already runs stable PR checks" in readme
    assert "Pull requests to `main` run" in agents
    assert "implemented in `.github/workflows/ci.yml`" in testing
    assert "Issue #14 owns the first executable CI implementation" not in testing
    assert "Once #14 establishes the first successful CI workflow" not in testing


def test_ticket_and_review_lifecycle_stays_single_pr_and_subagent_first() -> None:
    dependency = _read("docs/AGENT_WORKFLOW_DEPENDENCY.md").replace("\n", " ")
    testing = _read("docs/TESTING.md").replace("\n", " ")

    assert "one ticket branch/worktree and one implementation PR" in dependency
    assert "continue on that same PR" in dependency
    assert "do not silently create a replacement implementation PR" in dependency
    assert "Independent review is subagent-first and fail-closed" in dependency
    assert (
        "only after a concrete host/tool limitation has been established and recorded"
        in dependency
    )
    assert "One named ticket uses one implementation PR" in testing
    assert "separate review task/thread/worktree is a fallback" in testing
