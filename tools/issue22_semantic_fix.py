from pathlib import Path
from textwrap import dedent


trace = Path("src/bb_agent/trace.py")
text = trace.read_text(encoding="utf-8")

anchor = dedent(
    '''
    def _problem_payload(problem: Problem) -> dict[str, JsonValue]:
        return {
            "code": problem.code.value,
            "message": problem.message,
            "path": problem.path,
            "mechanic_id": problem.mechanic_id,
        }
    '''
).lstrip()
if anchor not in text:
    raise SystemExit("missing problem payload anchor")

helpers = dedent(
    '''

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
)
text = text.replace(anchor, anchor + helpers)

old_create = '''            "engine": engine,
            "generation": generation,
            "evaluations": list(evaluations),
            "selection": selection,
            "failure": failure,
'''
new_create = '''            "engine": engine,
            "generation": _semantic_generation_payload(generation),
            "evaluations": _semantic_evaluation_payloads(evaluations),
            "selection": selection,
            "failure": _semantic_failure_payload(failure),
'''
if text.count(old_create) != 1:
    raise SystemExit(f"unexpected create fingerprint block count: {text.count(old_create)}")
text = text.replace(old_create, new_create)

old_instance = '''            "engine": self.engine,
            "generation": self.generation,
            "evaluations": list(self.evaluations),
            "selection": self.selection,
            "failure": self.failure,
'''
new_instance = '''            "engine": self.engine,
            "generation": _semantic_generation_payload(self.generation),
            "evaluations": _semantic_evaluation_payloads(self.evaluations),
            "selection": self.selection,
            "failure": _semantic_failure_payload(self.failure),
'''
if text.count(old_instance) != 1:
    raise SystemExit(
        f"unexpected instance fingerprint block count: {text.count(old_instance)}"
    )
text = text.replace(old_instance, new_instance)

old_legal = dedent(
    '''
    def _legal_candidate_ids(trace: DecisionTrace) -> set[str]:
        actions = trace.generation.get("legal_candidates")
        if not isinstance(actions, Sequence) or isinstance(
            actions, str | bytes | bytearray
        ):
            return set()
        return {
            action_id
            for action in actions
            if isinstance(action, Mapping)
            and isinstance((action_id := action.get("action_id")), str)
        }
    '''
).lstrip()
new_legal = dedent(
    '''
    def _legal_candidate_ids(trace: DecisionTrace) -> set[str]:
        return set(_action_ids(trace.generation.get("legal_candidates")))
    '''
).lstrip()
if old_legal not in text:
    raise SystemExit("missing legal candidate helper")
text = text.replace(old_legal, new_legal)
trace.write_text(text, encoding="utf-8")


tests = Path("tests/test_trace.py")
text = tests.read_text(encoding="utf-8")
import_line = "from bb_agent.tactical_state import ActionKind, TacticalState\n"
import_block = dedent(
    '''
    from bb_agent.tactical_state import (
        ActionKind,
        AffordanceProvenance,
        ResolutionAuthority,
        TacticalState,
    )
    '''
).lstrip()
if import_line not in text:
    raise SystemExit("missing tactical_state import anchor")
text = text.replace(import_line, import_block)

addition = dedent(
    '''

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
)
if "test_affordance_provenance_metadata_does_not_change_semantic_trace_identity" in text:
    raise SystemExit("semantic provenance regression already present")
tests.write_text(text + addition, encoding="utf-8")


docs = Path("docs/TRACE.md")
text = docs.read_text(encoding="utf-8")
needle = "- `raw_capture_id` provenance/linkage labels (still retained in trace input);\n"
replacement = (
    needle
    + "- affordance capture/provenance/debug metadata and resolution-authority labels "
    "that the canonical state contract deliberately excludes from `state_id`;\n"
    + "- free-text diagnostic messages; stable status/error codes, paths and mechanic IDs "
    "remain in the semantic failure/coverage fingerprint;\n"
)
if needle not in text:
    raise SystemExit("missing deterministic identity documentation anchor")
text = text.replace(needle, replacement)
marker = (
    "This means two evaluations may report different nanosecond timings while still\n"
    "having exactly the same `output_fingerprint` and `trace_id`.\n"
)
detail = (
    "\nThe trace still preserves the complete diagnostic action/state records. "
    "For output identity, candidate generation is projected to stable legal action IDs "
    "and coverage codes, while candidate evaluations omit diagnostic action provenance "
    "and the documentation-only feature ownership table. The canonical `state_id` already "
    "commits to the semantic command costs/previews and decision input.\n"
)
if marker not in text:
    raise SystemExit("missing timing identity documentation marker")
text = text.replace(marker, marker + detail)
docs.write_text(text, encoding="utf-8")
