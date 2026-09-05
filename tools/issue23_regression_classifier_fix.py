from pathlib import Path

validation_path = Path("src/bb_agent/validation.py")
text = validation_path.read_text()
start = text.index("def classify_trace_change(")
end = text.index("\ndef _evaluate_expectations(", start)
replacement = '''def classify_trace_change(
    fixture: FixtureEnvelope,
    before: DecisionTrace,
    after: DecisionTrace,
) -> RegressionReport:
    """Classify a same-fixture semantic trace change under frozen #10 policy."""

    diff = compare_traces(before, after)
    normalized = fixture.normalized()
    fixture_state_id = normalized.state.state_id
    before_state_id = before.input.get("state_id")
    after_state_id = after.input.get("state_id")
    if before_state_id != fixture_state_id or after_state_id != fixture_state_id:
        return RegressionReport(
            RegressionKind.HARD_GATED_FAILURE,
            diff,
            "trace comparison must use the exact same canonical fixture state",
        )

    if before.output_fingerprint == after.output_fingerprint:
        return RegressionReport(
            RegressionKind.NO_CHANGE, diff, "semantic output unchanged"
        )

    expectations = (
        None
        if normalized.expectations is None
        else FixtureExpectations.from_json(normalized.expectations)
    )
    if expectations is not None:
        assertions = _evaluate_expectations(normalized, expectations, after)
        if any(
            item.gated and item.status is AssertionStatus.FAIL for item in assertions
        ):
            return RegressionReport(
                RegressionKind.HARD_GATED_FAILURE,
                diff,
                "current trace violates a gated fixture expectation",
            )

    if diff.added_action_ids or diff.removed_action_ids:
        return RegressionReport(
            RegressionKind.HARD_GATED_FAILURE,
            diff,
            "same-fixture legal candidate set changed without a ruleset/input change",
        )

    engine_changed = _engine_model_identity(before) != _engine_model_identity(after)
    if not engine_changed:
        return RegressionReport(
            RegressionKind.HARD_GATED_FAILURE,
            diff,
            "semantic output changed under identical engine/model/config identity",
        )

    disappeared = _disappeared_semantic_components(before, after)
    version_change_allowed = bool(
        expectations is not None and expectations.allow_model_version_change
    )
    if disappeared and not version_change_allowed:
        return RegressionReport(
            RegressionKind.HARD_GATED_FAILURE,
            diff,
            "previously modeled risk/explanation components disappeared: "
            + ", ".join(disappeared),
        )

    if expectations is not None:
        before_chosen = _chosen_action(before)
        after_chosen = _chosen_action(after)
        acceptable = set(expectations.acceptable_top1)
        if (
            before_chosen is not None
            and after_chosen is not None
            and before_chosen != after_chosen
            and before_chosen in acceptable
            and after_chosen in acceptable
        ):
            return RegressionReport(
                RegressionKind.ACCEPTABLE_SET_SUBSTITUTION,
                diff,
                "versioned recommendation changed between acceptable_top1 members",
            )

        if version_change_allowed:
            return RegressionReport(
                RegressionKind.INTENDED_MODEL_VERSION_CHANGE,
                diff,
                "versioned model/config identity changed and fixture permits it",
            )

    if normalized.metadata.severity is FixtureSeverity.CALIBRATION:
        return RegressionReport(
            RegressionKind.CALIBRATION_REVIEW_REQUIRED,
            diff,
            "calibration fixture changed and requires review without gating M1",
        )
    return RegressionReport(
        RegressionKind.REVIEW_REQUIRED_CHANGE,
        diff,
        "versioned semantic output changed while gated assertions still pass",
    )

'''
validation_path.write_text(text[:start] + replacement + text[end + 1 :])

text = validation_path.read_text()
marker = "\ndef _trace_duration_ns(trace: DecisionTrace) -> int | None:\n"
helpers = '''\ndef _semantic_component_inventory(trace: DecisionTrace) -> dict[str, set[str]]:
    inventory: dict[str, set[str]] = {}
    for action_id, record in _candidate_records(trace).items():
        identifiers: set[str] = set()
        evaluation = record.get("evaluation")
        if isinstance(evaluation, Mapping):
            components = evaluation.get("components")
            if isinstance(components, Sequence) and not isinstance(
                components, str | bytes | bytearray
            ):
                for component in components:
                    if isinstance(component, Mapping):
                        component_id = component.get("component_id")
                        if isinstance(component_id, str):
                            identifiers.add(f"component:{component_id}")
            explanation = evaluation.get("explanation_facts")
            if isinstance(explanation, Sequence) and not isinstance(
                explanation, str | bytes | bytearray
            ):
                for fact in explanation:
                    if isinstance(fact, Mapping):
                        component_id = fact.get("component_id")
                        if isinstance(component_id, str):
                            identifiers.add(f"explanation:{component_id}")
            if isinstance(evaluation.get("tail_risk"), Mapping):
                identifiers.add("risk:tail_risk")
            for field in ("uncertainty_span", "uncertainty_penalty"):
                value = evaluation.get(field)
                if isinstance(value, int | float) and not isinstance(value, bool):
                    identifiers.add(f"risk:{field}")
        inventory[action_id] = identifiers
    return inventory


def _disappeared_semantic_components(
    before: DecisionTrace, after: DecisionTrace
) -> tuple[str, ...]:
    before_inventory = _semantic_component_inventory(before)
    after_inventory = _semantic_component_inventory(after)
    disappeared = []
    for action_id in sorted(before_inventory.keys() & after_inventory.keys()):
        for identifier in sorted(
            before_inventory[action_id] - after_inventory[action_id]
        ):
            disappeared.append(f"{action_id}:{identifier}")
    return tuple(disappeared)

'''
if marker not in text:
    raise SystemExit("trace duration marker not found")
validation_path.write_text(text.replace(marker, helpers + marker, 1))

test_path = Path("tests/test_validation.py")
test_text = test_path.read_text()
test_text = test_text.replace(
    "from bb_agent.trace import run_decision_trace",
    "from bb_agent.trace import DecisionTrace, run_decision_trace",
)
helper_marker = "def _enemy_effect_only_profile(*, version=\"m1-evaluation-profile.v1\"):\n"
helpers = '''_UNSET = object()\n\n\ndef _rebuild_trace(\n    trace,\n    *,\n    engine=None,\n    generation=None,\n    evaluations=None,\n    selection=_UNSET,\n):\n    selection_value = trace.selection if selection is _UNSET else selection\n    return DecisionTrace.create(\n        input=dict(trace.input),\n        engine=dict(trace.engine if engine is None else engine),\n        generation=dict(trace.generation if generation is None else generation),\n        evaluations=tuple(\n            dict(item) for item in (trace.evaluations if evaluations is None else evaluations)\n        ),\n        selection=(\n            None if selection_value is None else dict(selection_value)\n        ),\n        failure=None if trace.failure is None else dict(trace.failure),\n        performance=dict(trace.performance),\n    )\n\n\ndef _versioned_engine(trace, suffix):\n    engine = dict(trace.engine)\n    engine[\"evaluation_config_version\"] = (\n        str(engine.get(\"evaluation_config_version\") or \"config\") + suffix\n    )\n    return engine\n\n\ndef _swapped_selection(trace):\n    assert trace.selection is not None\n    ranking = list(trace.selection[\"ranking\"])\n    assert len(ranking) >= 2\n    ranking[0], ranking[1] = ranking[1], ranking[0]\n    selection = dict(trace.selection)\n    selection[\"ranking\"] = ranking\n    selection[\"chosen_action_id\"] = ranking[0]\n    return selection\n\n\n'''
if helper_marker not in test_text:
    raise SystemExit("test helper marker not found")
test_text = test_text.replace(helper_marker, helpers + helper_marker, 1)
start = test_text.index("def test_regression_classification_distinguishes_frozen_categories():")
end = test_text.index("\ndef test_corpus_summary_reports_taxonomy_severity_and_nonblocking_reviews():", start)
new_test = '''def test_regression_classification_distinguishes_frozen_categories():
    authority = _authority()
    state = _snapshot(authority, _wait(), _wait(ActionKind.END_TURN))
    before = run_decision_trace(authority, state)
    assert before.selection is not None
    ranking = tuple(before.selection["ranking"])
    assert len(ranking) == 2

    version_fixture = _fixture(
        state,
        {
            "version": EXPECTATION_VERSION,
            "acceptable_top1": [before.selection["chosen_action_id"]],
            "allow_model_version_change": True,
        },
    )
    after_version = _rebuild_trace(
        before,
        engine=_versioned_engine(before, ".v2"),
    )
    intended = classify_trace_change(version_fixture, before, after_version)
    assert intended.kind is RegressionKind.INTENDED_MODEL_VERSION_CHANGE

    acceptable_fixture = _fixture(
        state,
        {
            "version": EXPECTATION_VERSION,
            "acceptable_top1": list(ranking),
            "allow_model_version_change": True,
        },
        fixture_id="acceptable-substitution",
    )
    after_substitution = _rebuild_trace(
        before,
        engine=_versioned_engine(before, ".substitution"),
        selection=_swapped_selection(before),
    )
    substitution = classify_trace_change(
        acceptable_fixture,
        before,
        after_substitution,
    )
    assert substitution.kind is RegressionKind.ACCEPTABLE_SET_SUBSTITUTION

    same_engine_substitution = _rebuild_trace(
        before,
        selection=_swapped_selection(before),
    )
    hard_same_engine = classify_trace_change(
        acceptable_fixture,
        before,
        same_engine_substitution,
    )
    assert hard_same_engine.kind is RegressionKind.HARD_GATED_FAILURE

    generation = dict(before.generation)
    generation["legal_candidates"] = list(generation["legal_candidates"]) + [
        {"action_id": "action:spurious-regression"}
    ]
    candidate_drift = _rebuild_trace(
        before,
        engine=_versioned_engine(before, ".candidate-drift"),
        generation=generation,
    )
    hard_candidate = classify_trace_change(
        acceptable_fixture,
        before,
        candidate_drift,
    )
    assert hard_candidate.kind is RegressionKind.HARD_GATED_FAILURE
    assert hard_candidate.diff.added_action_ids == ("action:spurious-regression",)

    evaluations = [dict(item) for item in before.evaluations]
    target = dict(evaluations[0])
    evaluation = dict(target["evaluation"])
    components = list(evaluation["components"])
    assert components
    removed_component_id = components[0]["component_id"]
    evaluation["components"] = components[1:]
    target["evaluation"] = evaluation
    evaluations[0] = target
    component_drift = _rebuild_trace(
        before,
        engine=_versioned_engine(before, ".component-drift"),
        evaluations=evaluations,
    )
    hard_component = classify_trace_change(
        _fixture(state, None, fixture_id="component-drift", review_status=ReviewStatus.DRAFT),
        before,
        component_drift,
    )
    assert hard_component.kind is RegressionKind.HARD_GATED_FAILURE
    assert removed_component_id in hard_component.message

    calibration_fixture = _fixture(
        state,
        None,
        fixture_id="calibration-change",
        severity=FixtureSeverity.CALIBRATION,
        review_status=ReviewStatus.DRAFT,
    )
    calibration_change = _rebuild_trace(
        before,
        engine=_versioned_engine(before, ".calibration"),
        selection=_swapped_selection(before),
    )
    calibration = classify_trace_change(
        calibration_fixture,
        before,
        calibration_change,
    )
    assert calibration.kind is RegressionKind.CALIBRATION_REVIEW_REQUIRED

    other_state = _snapshot(authority, _wait())
    other_trace = run_decision_trace(authority, other_state)
    cross_state = classify_trace_change(
        calibration_fixture,
        before,
        other_trace,
    )
    assert cross_state.kind is RegressionKind.HARD_GATED_FAILURE

'''
test_path.write_text(test_text[:start] + new_test + test_text[end + 1 :])
