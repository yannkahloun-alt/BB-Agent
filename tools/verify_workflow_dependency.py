"""Verify the required shared workflow checkout before validation starts."""

import subprocess
from pathlib import Path

EXPECTED_COMMIT = "4171010e1a17643876036b3dfd463b2e3a615c5f"
EXPECTED_URL = "https://github.com/yannkahloun-alt/codex-agent-workflow.git"
REQUIRED_FILES = (
    ".agent-workflow/AGENTS.md",
    ".agent-workflow/IMPLEMENTATION_AGENT.md",
    ".agent-workflow/CONTEXT_MANAGEMENT.md",
    ".agent-workflow/HANDOFF.md",
    "AGENTS.md",
)


def git(*args: str, root: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    missing = [path for path in REQUIRED_FILES if not (root / path).is_file()]
    if missing:
        raise SystemExit(f"missing required workflow files: {', '.join(missing)}")

    actual_url = git(
        "config",
        "--file",
        ".gitmodules",
        "--get",
        "submodule..agent-workflow.url",
        root=root,
    )
    if actual_url != EXPECTED_URL:
        raise SystemExit(f"unexpected workflow URL: {actual_url}")

    actual_commit = git("-C", ".agent-workflow", "rev-parse", "HEAD", root=root)
    if actual_commit != EXPECTED_COMMIT:
        raise SystemExit(
            f"unexpected workflow pin: {actual_commit}; expected {EXPECTED_COMMIT}"
        )

    recorded_commit = git("rev-parse", "HEAD:.agent-workflow", root=root)
    if recorded_commit != EXPECTED_COMMIT:
        raise SystemExit(
            "unexpected recorded workflow pin: "
            f"{recorded_commit}; expected {EXPECTED_COMMIT}"
        )

    print(f"workflow dependency verified at {actual_commit}")


if __name__ == "__main__":
    main()
