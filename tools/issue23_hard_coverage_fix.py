from pathlib import Path

validation = Path("src/bb_agent/validation.py")
text = validation.read_text(encoding="utf-8")
old = '''    if expectations.expected_status is not None:
        results.append(
            _policy_assertion(
                "expected_status",
                actual_status == expectations.expected_status,
                tactical_gate,
                f"decision status is {actual_status!r}; expected "
                f"{expectations.expected_status!r}",
            )
        )

    if expectations.has_ranking_assertions:
        results.append(
            _policy_assertion(
                "ranking_available",
                actual_status == "SUCCESS" and trace.selection is not None,
                tactical_gate,
                "ranking expectations require a successful complete-coverage decision",
            )
        )
'''
new = '''    if expectations.expected_status is not None:
        results.append(
            _hard_assertion(
                "expected_status",
                actual_status == expectations.expected_status,
                f"decision status is {actual_status!r}; expected "
                f"{expectations.expected_status!r}",
            )
        )

    if expectations.has_ranking_assertions:
        results.append(
            _hard_assertion(
                "ranking_available",
                actual_status == "SUCCESS" and trace.selection is not None,
                "ranking expectations require a successful complete-coverage decision",
            )
        )
'''
if text.count(old) != 1:
    raise SystemExit(f"unexpected coverage assertion block count: {text.count(old)}")
validation.write_text(text.replace(old, new, 1), encoding="utf-8")

tests = Path("tests/test_validation.py")
text = tests.read_text(encoding="utf-8")
if "test_calibration_still_hard_fails_status_and_missing_ranking_coverage" in text:
    raise SystemExit("hard-coverage regression already exists")
addition = '''


def test_calibration_still_hard_fails_status_and_missing_ranking_coverage():
    authority = _authority()
    state = _snapshot(authority, _wait(), _attack("mod.unknown_aoe"))
    status_fixture = _fixture(
        state,
        {"version": EXPECTATION_VERSION, "expected_status": "SUCCESS"},
        fixture_id="calibration-status",
        severity=FixtureSeverity.CALIBRATION,
        review_status=ReviewStatus.REVIEWED,
    )
    ranking_fixture = _fixture(
        state,
        {
            "version": EXPECTATION_VERSION,
            "acceptable_top1": [state.action_affordances.actions[0].action_id],
        },
        fixture_id="calibration-ranking-coverage",
        severity=FixtureSeverity.CALIBRATION,
        review_status=ReviewStatus.REVIEWED,
    )

    status_report = run_fixture_validation(authority, status_fixture)
    ranking_report = run_fixture_validation(authority, ranking_fixture)

    assert status_report.passed is False
    status_assertion = next(
        item
        for item in status_report.assertions
        if item.assertion_id == "expected_status"
    )
    assert status_assertion.status is AssertionStatus.FAIL
    assert status_assertion.gated is True

    assert ranking_report.passed is False
    ranking_assertion = next(
        item
        for item in ranking_report.assertions
        if item.assertion_id == "ranking_available"
    )
    assert ranking_assertion.status is AssertionStatus.FAIL
    assert ranking_assertion.gated is True
'''
tests.write_text(text + addition, encoding="utf-8")

doc = Path("docs/VALIDATION.md")
text = doc.read_text(encoding="utf-8")
old_doc = '''For `CORE`, `QUALITY`, and `SAFETY_CRITICAL` fixtures, tactical expectation failures (`acceptable_top1`, forbidden top1, ordering, top-K, near ties, component/risk relations, information sensitivity, explanation IDs) are gated failures.

For `CALIBRATION` fixtures, the same tactical mismatches are emitted as `REVIEW` findings and do not by themselves fail M1 acceptance. Structural/replay/legality corruption still fails even on a calibration fixture.
'''
new_doc = '''For `CORE`, `QUALITY`, and `SAFETY_CRITICAL` fixtures, tactical expectation failures (`acceptable_top1`, forbidden top1, ordering, top-K, near ties, component/risk relations, information sensitivity, explanation IDs) are gated failures.

For `CALIBRATION` fixtures, those tactical-value/ranking disagreements are emitted as `REVIEW` findings and do not by themselves fail M1 acceptance. Structural/replay/legality/coverage correctness remains hard on every severity: an explicit decision-status assertion is always gated, and any fixture that asks for ranking semantics must actually produce a successful complete-coverage ranking.
'''
if old_doc not in text:
    raise SystemExit("missing calibration gate documentation anchor")
doc.write_text(text.replace(old_doc, new_doc, 1), encoding="utf-8")
