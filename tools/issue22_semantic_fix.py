from pathlib import Path


trace = Path("src/bb_agent/trace.py")
text = trace.read_text(encoding="utf-8")

marker = "\n\n@dataclass(frozen=True, slots=True)\nclass DecisionTrace:"
if marker not in text:
    raise SystemExit("missing DecisionTrace marker")

helpers = r'''


def _action_ids(actions: JsonValue) -> tuple[str, ...]:
    if not isinstance(actions, Sequence) or isinstance(
        actions, str | bytes | bytearray
    ):
        return ()
    action_ids = []
    for action in actions:
        if isinstance(action, Mapping):
            action_id = action.get("action_id")
            if isinstance(action_id, str):
                action_ids.append(action_id)
    return tuple(sorted(action_ids))


def _stable_problem_payloads(problems: JsonValue) -> list[dict[str, JsonValue]]:
    if not isinstance(problems, Sequence) or isinstance(
        problems, str | bytes | bytearray
    ):
        return []
    result = []
    for problem in problems:
        if not isinstance(problem, Mapping):
            continue
        result.append(
            {
                "code": problem.get("code"),
                "path": problem.get("path"),
                "mechanic_id": problem.get("mechanic_id"),
                "exception_type": problem.get("exception_type"),
            }
        )
    result.sort(
        key=lambda item: tuple(
            str(item.get(key) or "")
            for key in ("code", "path", "mechanic_id", "exception_type")
        )
    )
    return result


def _semantic_generation_payload(
    generation: Mapping[str, JsonValue],
) -> dict[str, JsonValue]:
    return {
        "decision_status": generation.get("decision_status"),
        "legal_candidate_ids": list(_action_ids(generation.get("legal_candidates"))),
        "rejected_probe_counts": generation.get("rejected_probe_counts"),
        "indeterminate_count": generation.get("indeterminate_count"),
        "coverage_diagnostics": _stable_problem_payloads(
            generation.get("coverage_diagnostics")
        ),
    }


def _semantic_evaluation_payloads(
    evaluations: Sequence[Mapping[str, JsonValue]],
) -> list[dict[str, JsonValue]]:
    result = []
    for record in evaluations:
        payload: dict[str, JsonValue] = {
            "action_id": record.get("action_id"),
            "coverage_status": record.get("coverage_status"),
            "outcome": record.get("outcome"),
        }
        evaluation = record.get("evaluation")
        if isinstance(evaluation, Mapping):
            evaluation_payload = dict(evaluation)
            features = evaluation_payload.get("features")
            if isinstance(features, Mapping):
                feature_payload = dict(features)
                feature_payload.pop("semantic_ownership", None)
                evaluation_payload["features"] = feature_payload
            payload["evaluation"] = evaluation_payload
        result.append(payload)
    result.sort(key=lambda item: str(item.get("action_id") or ""))
    return result


def _semantic_failure_payload(
    failure: Mapping[str, JsonValue] | None,
) -> dict[str, JsonValue] | None:
    if failure is None:
        return None
    return {
        "stage": failure.get("stage"),
        "status": failure.get("status"),
        "problems": _stable_problem_payloads(failure.get("problems")),
    }
'''
if "def _semantic_generation_payload(" in text:
    raise SystemExit("semantic helpers already present")
text = text.replace(marker, helpers + marker, 1)

create_old = '''            "engine": engine,
            "generation": generation,
            "evaluations": list(evaluations),
            "selection": selection,
            "failure": failure,
'''
create_new = '''            "engine": engine,
            "generation": _semantic_generation_payload(generation),
            "evaluations": _semantic_evaluation_payloads(evaluations),
            "selection": selection,
            "failure": _semantic_failure_payload(failure),
'''
create_start = text.index("    @classmethod\n    def create(")
create_end = text.index("\n    def _fingerprint_payload(", create_start)
create_section = text[create_start:create_end]
if create_section.count(create_old) != 1:
    raise SystemExit("create fingerprint payload shape changed")
create_section = create_section.replace(create_old, create_new, 1)
text = text[:create_start] + create_section + text[create_end:]

fp_start = text.index("    def _fingerprint_payload(")
fp_end = text.index("\n    def to_dict(", fp_start)
fp_section = text[fp_start:fp_end]
instance_old = '''            "engine": self.engine,
            "generation": self.generation,
            "evaluations": list(self.evaluations),
            "selection": self.selection,
            "failure": self.failure,
'''
instance_new = '''            "engine": self.engine,
            "generation": _semantic_generation_payload(self.generation),
            "evaluations": _semantic_evaluation_payloads(self.evaluations),
            "selection": self.selection,
            "failure": _semantic_failure_payload(self.failure),
'''
if fp_section.count(instance_old) != 1:
    raise SystemExit("instance fingerprint payload shape changed")
fp_section = fp_section.replace(instance_old, instance_new, 1)
text = text[:fp_start] + fp_section + text[fp_end:]

legal_start = text.index("def _legal_candidate_ids(trace: DecisionTrace) -> set[str]:")
legal_end = text.index("\n\ndef _component_values(", legal_start)
text = (
    text[:legal_start]
    + "def _legal_candidate_ids(trace: DecisionTrace) -> set[str]:\n"
    + "    return set(_action_ids(trace.generation.get(\"legal_candidates\")))\n"
    + text[legal_end:]
)
trace.write_text(text, encoding="utf-8")


tests = Path("tests/test_trace.py")
text = tests.read_text(encoding="utf-8")
old_import = "from bb_agent.tactical_state import ActionKind, TacticalState\n"
new_import = '''from bb_agent.tactical_state import (
    ActionKind,
    AffordanceProvenance,
    ResolutionAuthority,
    TacticalState,
)
'''
if old_import not in text:
    raise SystemExit("tactical_state import shape changed")
text = text.replace(old_import, new_import, 1)

addition = r'''


def _with_affordance_diagnostic_metadata(
    state: TacticalState,
    source_generation: str,
    provenance: AffordanceProvenance,
    authority: ResolutionAuthority,
) -> TacticalState:
    actions = []
    for action in state.action_affordances.actions:
        changes = {
            "source_generation": source_generation,
            "provenance": provenance,
        }
        for field_name in (
            "ap_cost",
            "fatigue_cost",
            "charge_cost",
            "ammo_cost",
            "item_action_cost",
        ):
            cost = getattr(action, field_name)
            if cost is not None:
                changes[field_name] = replace(cost, authority=authority)
        actions.append(replace(action, **changes))
    affordances = replace(
        state.action_affordances,
        source_generation=source_generation,
        actions=tuple(actions),
    )
    values = {field.name: getattr(state, field.name) for field in fields(state)}
    values.update(state_id="", action_affordances=affordances)
    return TacticalState.create(**values)


def test_affordance_provenance_metadata_does_not_change_semantic_trace_identity():
    authority = _authority()
    base = _ordinary_attack_state(authority)
    fixture_state = _with_affordance_diagnostic_metadata(
        base,
        "fixture-generation-a",
        AffordanceProvenance.HANDCRAFTED_FIXTURE,
        ResolutionAuthority.HANDCRAFTED_FIXTURE,
    )
    game_state = _with_affordance_diagnostic_metadata(
        base,
        "game-generation-b",
        AffordanceProvenance.GAME_PLAYER_AFFORDANCE,
        ResolutionAuthority.GAME_PLAYER_AFFORDANCE,
    )

    assert fixture_state.state_id == game_state.state_id
    assert tuple(
        action.action_id for action in fixture_state.action_affordances.actions
    ) == tuple(action.action_id for action in game_state.action_affordances.actions)

    fixture_trace = run_decision_trace(authority, fixture_state)
    game_trace = run_decision_trace(authority, game_state)

    assert fixture_trace.input["canonical_state"] != game_trace.input["canonical_state"]
    assert fixture_trace.selection == game_trace.selection
    assert fixture_trace.output_fingerprint == game_trace.output_fingerprint
    assert fixture_trace.trace_id == game_trace.trace_id
'''
if "test_affordance_provenance_metadata_does_not_change_semantic_trace_identity" in text:
    raise SystemExit("semantic provenance regression already present")
tests.write_text(text + addition, encoding="utf-8")


docs = Path("docs/TRACE.md")
text = docs.read_text(encoding="utf-8")
needle = "- `raw_capture_id` provenance/linkage labels (still retained in trace input);\n"
if needle not in text:
    raise SystemExit("deterministic identity documentation shape changed")
replacement = (
    needle
    + "- affordance capture/provenance/debug metadata and resolution-authority labels "
    "that the canonical state contract deliberately excludes from `state_id`;\n"
    + "- free-text diagnostic messages; stable status/error codes, paths and mechanic IDs "
    "remain in the semantic failure/coverage fingerprint;\n"
)
text = text.replace(needle, replacement, 1)
marker = (
    "This means two evaluations may report different nanosecond timings while still\n"
    "having exactly the same `output_fingerprint` and `trace_id`.\n"
)
if marker not in text:
    raise SystemExit("timing identity documentation shape changed")
detail = (
    "\nThe trace still preserves the complete diagnostic action/state records. "
    "For output identity, candidate generation is projected to stable legal action IDs "
    "and coverage codes, while candidate evaluations omit diagnostic action provenance "
    "and the documentation-only feature ownership table. The canonical `state_id` already "
    "commits to the semantic command costs/previews and decision input.\n"
)
text = text.replace(marker, marker + detail, 1)
docs.write_text(text, encoding="utf-8")
