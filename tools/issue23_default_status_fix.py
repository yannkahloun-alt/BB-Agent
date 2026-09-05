from pathlib import Path

validation_path = Path("src/bb_agent/validation.py")
validation = validation_path.read_text()

old_none = '''    if expectations is None:\n        if normalized.metadata.review_status is not ReviewStatus.PROMOTED:\n            assertions.append(\n                ValidationAssertion(\n                    "expectations_present",\n                    AssertionStatus.REVIEW,\n                    False,\n                    "fixture has no semantic expectations yet",\n                )\n            )\n    else:\n        assertions.extend(_evaluate_expectations(normalized, expectations, trace))\n'''
new_none = '''    if expectations is None:\n        actual_status = str(trace.generation.get("decision_status") or "")\n        assertions.append(\n            _hard_assertion(\n                "expected_status",\n                actual_status == "SUCCESS",\n                f"decision status is {actual_status!r}; expected 'SUCCESS'",\n            )\n        )\n        if normalized.metadata.review_status is not ReviewStatus.PROMOTED:\n            assertions.append(\n                ValidationAssertion(\n                    "expectations_present",\n                    AssertionStatus.REVIEW,\n                    False,\n                    "fixture has no semantic expectations yet",\n                )\n            )\n    else:\n        assertions.extend(_evaluate_expectations(normalized, expectations, trace))\n'''
if validation.count(old_none) != 1:
    raise SystemExit("unexpected expectations-none block")
validation = validation.replace(old_none, new_none)

old_status = '''    if expectations.expected_status is not None:\n        results.append(\n            _hard_assertion(\n                "expected_status",\n                actual_status == expectations.expected_status,\n                f"decision status is {actual_status!r}; expected "\n                f"{expectations.expected_status!r}",\n            )\n        )\n'''
new_status = '''    expected_status = expectations.expected_status or "SUCCESS"\n    results.append(\n        _hard_assertion(\n            "expected_status",\n            actual_status == expected_status,\n            f"decision status is {actual_status!r}; expected {expected_status!r}",\n        )\n    )\n'''
if validation.count(old_status) != 1:
    raise SystemExit("unexpected expected-status block")
validation = validation.replace(old_status, new_status)
validation_path.write_text(validation)

test_path = Path("tests/test_validation.py")
tests = test_path.read_text()
anchor = '''def test_oracle_affordance_completeness_metadata_is_checked_generically():\n'''
new_test = '''def test_nonranking_expectations_default_to_success_and_hard_fail_coverage():\n    authority = _authority()\n    state = _snapshot(authority, _wait(), _attack("mod.unknown_aoe"))\n    legal_ids = [action.action_id for action in state.action_affordances.actions]\n    payload = {\n        "version": EXPECTATION_VERSION,\n        "exact_legal_action_ids": legal_ids,\n    }\n    parsed = FixtureExpectations.from_json(payload)\n    assert parsed.expected_status is None\n    assert parsed.has_ranking_assertions is False\n\n    cases = (\n        (FixtureSeverity.CORE, ReviewStatus.PROMOTED),\n        (FixtureSeverity.CALIBRATION, ReviewStatus.REVIEWED),\n    )\n    for severity, review_status in cases:\n        fixture = _fixture(\n            state,\n            payload,\n            fixture_id=f"unexpected-coverage-{severity.value.lower()}",\n            severity=severity,\n            review_status=review_status,\n        )\n        report = run_fixture_validation(authority, fixture)\n\n        assert report.trace is not None\n        assert report.trace.generation["decision_status"] == "INCOMPLETE_COVERAGE"\n        assert report.passed is False\n        status = next(\n            item\n            for item in report.assertions\n            if item.assertion_id == "expected_status"\n        )\n        assert status.status is AssertionStatus.FAIL\n        assert status.gated is True\n\n\n'''
if tests.count(anchor) != 1:
    raise SystemExit("unexpected oracle-test anchor")
tests = tests.replace(anchor, new_test + anchor)
test_path.write_text(tests)

doc_path = Path("docs/VALIDATION.md")
doc = doc_path.read_text()
old_doc = '''An `INCOMPLETE_COVERAGE` fixture can explicitly assert that status and its mechanic/error diagnostics. Any fixture carrying ranking assertions implicitly requires a successful complete-coverage ranking; the harness therefore fails closed rather than scoring around unsupported legal affordances.\n'''
new_doc = '''Decision status is always a hard assertion. When `expected_status` is omitted, the harness implicitly expects `SUCCESS`; omission never disables coverage gating. A dedicated failure/coverage fixture must explicitly declare its expected non-success status, such as `INCOMPLETE_COVERAGE`, together with any mechanic/error diagnostics it wants to assert. Any fixture carrying ranking assertions likewise requires a successful complete-coverage ranking, so the harness fails closed rather than scoring around unsupported legal affordances.\n'''
if doc.count(old_doc) != 1:
    raise SystemExit("unexpected validation-doc status paragraph")
doc = doc.replace(old_doc, new_doc)
doc_path.write_text(doc)
