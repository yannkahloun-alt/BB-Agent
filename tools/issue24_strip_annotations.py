from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from bb_agent.fixtures import FixtureEnvelope, load_fixture, save_fixture  # noqa: E402
from bb_agent.results import ResultStatus  # noqa: E402
from bb_agent.validation import run_validation_corpus  # noqa: E402
from test_mechanics import _authority  # noqa: E402

CORPUS_DIR = Path("tests/fixtures/ticket_24")
TEST_PATH = Path("tests/test_core_safety_corpus.py")


def main() -> None:
    fixtures = []
    changed = 0
    for path in sorted(CORPUS_DIR.glob("*.json")):
        loaded = load_fixture(path)
        assert loaded.status is ResultStatus.SUCCESS, loaded.problems
        assert loaded.value is not None
        fixture = loaded.value
        old_state_id = fixture.state.state_id
        if fixture.state.annotations is not None:
            changed += 1
        state = replace(fixture.state, annotations=None).normalized()
        assert state.state_id == old_state_id
        clean = FixtureEnvelope.create(
            metadata=fixture.metadata,
            state=state,
            expectations=fixture.expectations,
            oracle_annotations=fixture.oracle_annotations,
        )
        assert clean.state_hash == fixture.state_hash
        result = save_fixture(path, clean)
        assert result.status is ResultStatus.SUCCESS, result.problems
        fixtures.append(clean)

    assert len(fixtures) == 25
    assert changed > 0
    assert all(fixture.state.annotations is None for fixture in fixtures)

    report = run_validation_corpus(_authority(), fixtures)
    assert report.passed, report.blocking_failures

    text = TEST_PATH.read_text()
    needle = '        assert provenance["evidence"]\n'
    replacement = needle + "        assert fixture.state.annotations is None\n"
    if needle not in text:
        raise SystemExit("permanent provenance assertion anchor not found")
    if "assert fixture.state.annotations is None" not in text:
        TEST_PATH.write_text(text.replace(needle, replacement, 1))

    print(f"stripped helper annotations from {changed} of 25 fixtures")


if __name__ == "__main__":
    main()
