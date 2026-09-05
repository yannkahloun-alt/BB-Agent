"""Machine-readable decision traces, exact replay, and regression diagnostics."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Any

from bb_agent.evaluator import (
    CONFIG_VERSION,
    MODEL_VERSION as EVALUATOR_MODEL_VERSION,
    DEFAULT_EVALUATION_PROFILE,
    DEFAULT_UNIT_VALUE_POLICY,
    CandidateEvaluation,
    DecisionEvaluation,
    EvaluationProfile,
    EvaluationScales,
    EvaluationWeights,
    UnitValuePolicy,
    evaluate_decision,
)
from bb_agent.fixtures import FixtureEnvelope, ReplayInput
from bb_agent.mechanics import MechanicsAuthority
from bb_agent.results import ErrorCode, Problem, ResultStatus
from bb_agent.serialization import JsonValue, canonical_json_bytes, canonical_sha256
from bb_agent.tactical_state import TacticalState
from bb_agent.versions import CURRENT_VERSIONS

TRACE_VERSION = "bb-agent-decision-trace.v1"


def _jsonify(value: Any) -> JsonValue:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            field.name: _jsonify(getattr(value, field.name)) for field in fields(value)
        }
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("trace mappings require string keys")
            result[key] = _jsonify(child)
        return result
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_jsonify(child) for child in value]
    raise TypeError(f"unsupported trace value: {type(value).__name__}")


def _object(value: JsonValue, name: str) -> dict[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    result: dict[str, JsonValue] = {}
    for key, child in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{name} contains a non-string key")
        result[key] = child
    return result


def _string(value: JsonValue, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _problem_payload(problem: Problem) -> dict[str, JsonValue]:
    return {
        "code": problem.code.value,
        "message": problem.message,
        "path": problem.path,
        "mechanic_id": problem.mechanic_id,
    }


@dataclass(frozen=True, slots=True)
class DecisionTrace:
    trace_version: str
    trace_id: str
    input: dict[str, JsonValue]
    engine: dict[str, JsonValue]
    generation: dict[str, JsonValue]
    evaluations: tuple[dict[str, JsonValue], ...]
    selection: dict[str, JsonValue] | None
    failure: dict[str, JsonValue] | None
    performance: dict[str, JsonValue]
    output_fingerprint: str

    def __post_init__(self) -> None:
        if self.trace_version != TRACE_VERSION:
            raise ValueError("unsupported decision trace version")
        canonical_json_bytes(self.input)
        canonical_json_bytes(self.engine)
        canonical_json_bytes(self.generation)
        canonical_json_bytes(self.evaluations)
        canonical_json_bytes(self.selection)
        canonical_json_bytes(self.failure)
        canonical_json_bytes(self.performance)
        expected = canonical_sha256(self._fingerprint_payload())
        if self.output_fingerprint != expected:
            raise ValueError(
                "decision trace output_fingerprint does not match semantic output"
            )
        expected_trace_id = canonical_sha256(
            {
                "trace_version": self.trace_version,
                "state_id": self.input.get("state_id"),
                "output_fingerprint": self.output_fingerprint,
            }
        )
        if self.trace_id != expected_trace_id:
            raise ValueError("decision trace_id does not match trace identity")

    @classmethod
    def create(
        cls,
        *,
        input: dict[str, JsonValue],
        engine: dict[str, JsonValue],
        generation: dict[str, JsonValue],
        evaluations: tuple[dict[str, JsonValue], ...],
        selection: dict[str, JsonValue] | None,
        failure: dict[str, JsonValue] | None,
        performance: dict[str, JsonValue],
    ) -> "DecisionTrace":
        payload = {
            "trace_version": TRACE_VERSION,
            "input_identity": {
                "state_id": input.get("state_id"),
                "raw_capture_id": input.get("raw_capture_id"),
                "information_profile": input.get("information_profile"),
                "ruleset_content_fingerprint": input.get("ruleset_content_fingerprint"),
            },
            "engine": engine,
            "generation": generation,
            "evaluations": list(evaluations),
            "selection": selection,
            "failure": failure,
        }
        output_fingerprint = canonical_sha256(payload)
        trace_id = canonical_sha256(
            {
                "trace_version": TRACE_VERSION,
                "state_id": input.get("state_id"),
                "output_fingerprint": output_fingerprint,
            }
        )
        return cls(
            TRACE_VERSION,
            trace_id,
            input,
            engine,
            generation,
            evaluations,
            selection,
            failure,
            performance,
            output_fingerprint,
        )

    def _fingerprint_payload(self) -> dict[str, JsonValue]:
        return {
            "trace_version": self.trace_version,
            "input_identity": {
                "state_id": self.input.get("state_id"),
                "raw_capture_id": self.input.get("raw_capture_id"),
                "information_profile": self.input.get("information_profile"),
                "ruleset_content_fingerprint": self.input.get(
                    "ruleset_content_fingerprint"
                ),
            },
            "engine": self.engine,
            "generation": self.generation,
            "evaluations": list(self.evaluations),
            "selection": self.selection,
            "failure": self.failure,
        }

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "trace_version": self.trace_version,
            "trace_id": self.trace_id,
            "input": self.input,
            "engine": self.engine,
            "generation": self.generation,
            "evaluations": list(self.evaluations),
            "selection": self.selection,
            "failure": self.failure,
            "performance": self.performance,
            "output_fingerprint": self.output_fingerprint,
        }

    def to_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict()) + b"\n"

    @classmethod
    def from_dict(cls, value: Mapping[str, JsonValue]) -> "DecisionTrace":
        required = {
            "trace_version",
            "trace_id",
            "input",
            "engine",
            "generation",
            "evaluations",
            "selection",
            "failure",
            "performance",
            "output_fingerprint",
        }
        if set(value) != required:
            raise ValueError("decision trace fields do not match schema")
        evaluations_value = value["evaluations"]
        if not isinstance(evaluations_value, Sequence) or isinstance(
            evaluations_value, str | bytes | bytearray
        ):
            raise ValueError("decision trace evaluations must be a sequence")
        return cls(
            _string(value["trace_version"], "trace_version"),
            _string(value["trace_id"], "trace_id"),
            _object(value["input"], "input"),
            _object(value["engine"], "engine"),
            _object(value["generation"], "generation"),
            tuple(_object(item, "evaluation") for item in evaluations_value),
            (
                None
                if value["selection"] is None
                else _object(value["selection"], "selection")
            ),
            None if value["failure"] is None else _object(value["failure"], "failure"),
            _object(value["performance"], "performance"),
            _string(value["output_fingerprint"], "output_fingerprint"),
        )

    @classmethod
    def from_json_bytes(cls, payload: bytes | bytearray | str) -> "DecisionTrace":
        try:
            decoded = json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid decision trace JSON: {exc}") from exc
        if not isinstance(decoded, dict):
            raise ValueError("decision trace JSON root must be an object")
        return cls.from_dict(decoded)


@dataclass(frozen=True, slots=True)
class TraceReplayResult:
    matches: bool
    expected_output_fingerprint: str
    actual_output_fingerprint: str
    ranking_matches: bool
    chosen_action_matches: bool
    actual_trace: DecisionTrace


@dataclass(frozen=True, slots=True)
class RankDelta:
    action_id: str
    before_rank: int | None
    after_rank: int | None


@dataclass(frozen=True, slots=True)
class ComponentDelta:
    action_id: str
    component_id: str
    before: float
    after: float
    delta: float


@dataclass(frozen=True, slots=True)
class TraceDiff:
    chosen_action_changed: bool
    output_fingerprint_changed: bool
    added_action_ids: tuple[str, ...]
    removed_action_ids: tuple[str, ...]
    rank_deltas: tuple[RankDelta, ...]
    component_deltas: tuple[ComponentDelta, ...]


def _coerce_source(
    source: FixtureEnvelope | ReplayInput | TacticalState,
) -> tuple[str | None, TacticalState]:
    if isinstance(source, FixtureEnvelope):
        replay = source.replay_input()
        return replay.fixture_id, replay.state
    if isinstance(source, ReplayInput):
        return source.fixture_id, source.state
    if isinstance(source, TacticalState):
        return None, source
    raise TypeError(
        "decision trace source must be FixtureEnvelope, ReplayInput, or TacticalState"
    )


def _safe_normalized_state(state: TacticalState) -> TacticalState | None:
    try:
        return state.normalized()
    except (TypeError, ValueError):
        return None


def _state_payload(
    state: TacticalState, normalized: TacticalState | None
) -> dict[str, JsonValue]:
    candidate = normalized if normalized is not None else state
    try:
        value = _jsonify(candidate.to_dict())
        assert isinstance(value, dict)
        return value
    except (TypeError, ValueError, AssertionError):
        return {
            "contract_version": getattr(candidate, "contract_version", "unknown"),
            "state_id": getattr(candidate, "state_id", ""),
        }


def _input_payload(
    fixture_id: str | None,
    state: TacticalState,
    normalized: TacticalState | None,
) -> dict[str, JsonValue]:
    canonical_state = _state_payload(state, normalized)
    source = normalized if normalized is not None else state
    ruleset = getattr(source, "ruleset", None)
    return {
        "fixture_id": fixture_id,
        "state_id": getattr(source, "state_id", ""),
        "raw_capture_id": getattr(source, "raw_capture_id", None),
        "contract_version": getattr(source, "contract_version", "unknown"),
        "information_profile": (
            getattr(getattr(source, "information_profile", None), "value", "unknown")
        ),
        "ruleset_game_version": getattr(ruleset, "game_version", "unknown"),
        "ruleset_content_fingerprint": getattr(
            ruleset, "content_fingerprint", "unknown"
        ),
        "canonical_state": canonical_state,
    }


def _engine_payload(
    authority: MechanicsAuthority,
    profile: EvaluationProfile,
    unit_value_policy: UnitValuePolicy,
    evaluation: DecisionEvaluation | None,
    implementation_revision: str | None,
) -> dict[str, JsonValue]:
    outcome_versions = (
        sorted(
            {
                candidate.features.outcome_model_version
                for candidate in evaluation.candidates
            }
        )
        if evaluation is not None
        else []
    )
    sample_count = (
        sum(
            candidate.features.outcome_facts.sample_count
            for candidate in evaluation.candidates
        )
        if evaluation is not None
        else 0
    )
    return {
        "implementation_revision": implementation_revision,
        "contract_versions": _jsonify(CURRENT_VERSIONS.as_mapping()),
        "trace_schema_version": TRACE_VERSION,
        "evaluator_version": EVALUATOR_MODEL_VERSION,
        "evaluation_config_version": CONFIG_VERSION,
        "evaluation_profile": _jsonify(profile),
        "evaluation_profile_fingerprint": profile.fingerprint,
        "unit_value_policy": _jsonify(unit_value_policy),
        "unit_value_policy_fingerprint": unit_value_policy.fingerprint,
        "mechanics_manifest_version": CURRENT_VERSIONS.mechanics_manifest,
        "mechanics_manifest_fingerprint": authority.manifest.fingerprint,
        "declared_outcome_model_version": CURRENT_VERSIONS.outcome_model,
        "outcome_model_versions": outcome_versions,
        "simulator_settings": {
            "mode": "exact_or_analytic_current_models",
            "seeds": [],
            "sample_count": sample_count,
        },
    }


def _actions_from_state_payload(
    state_payload: dict[str, JsonValue],
) -> tuple[dict[str, JsonValue], ...]:
    affordances = state_payload.get("action_affordances")
    if not isinstance(affordances, Mapping):
        return ()
    actions = affordances.get("actions")
    if not isinstance(actions, Sequence) or isinstance(
        actions, str | bytes | bytearray
    ):
        return ()
    return tuple(_object(action, "action") for action in actions)


def _candidate_trace(
    candidate: CandidateEvaluation,
    action: dict[str, JsonValue] | None,
) -> dict[str, JsonValue]:
    outcome = candidate.features.outcome_facts
    deterministic_costs = {}
    if action is not None:
        for field_name in (
            "ap_cost",
            "fatigue_cost",
            "ammo_cost",
            "charge_cost",
            "item_action_cost",
        ):
            deterministic_costs[field_name] = action.get(field_name)
    return {
        "action_id": candidate.action_id,
        "action": action,
        "deterministic_costs": deterministic_costs,
        "outcome": _jsonify(outcome),
        "evaluation": _jsonify(candidate),
    }


def _selection_payload(evaluation: DecisionEvaluation) -> dict[str, JsonValue]:
    candidates = {candidate.action_id: candidate for candidate in evaluation.candidates}
    runner_up = None
    if len(evaluation.ranking) > 1:
        winner = candidates[evaluation.ranking[0]]
        second = candidates[evaluation.ranking[1]]
        runner_up = {
            "action_id": second.action_id,
            "ranking_value_delta": winner.ranking_value - second.ranking_value,
            "tail_risk_delta": (
                winner.tail_risk.selection_penalty - second.tail_risk.selection_penalty
            ),
        }
    return {
        "chosen_action_id": evaluation.chosen_action_id,
        "ranking": list(evaluation.ranking),
        "near_ties": _jsonify(evaluation.near_tie_groups),
        "tie_breaks": _jsonify(evaluation.tie_breaks),
        "dominance_findings": [
            {"action_id": candidate.action_id, "dominated_by": candidate.dominated_by}
            for candidate in evaluation.candidates
            if candidate.dominated_by is not None
        ],
        "guardrail_findings": [
            {
                "action_id": candidate.action_id,
                "findings": list(candidate.guardrail_findings),
            }
            for candidate in evaluation.candidates
            if candidate.guardrail_findings
        ],
        "information_sensitive": evaluation.information_sensitive,
        "epistemic_scenarios": _jsonify(evaluation.epistemic_scenarios),
        "runner_up": runner_up,
    }


def _failure_stage(status: ResultStatus, timings: Mapping[str, int]) -> str:
    if status is ResultStatus.VALIDATION_FAILURE:
        return "validation"
    if "outcome_and_features" in timings:
        return "outcome_and_features"
    if "coverage" in timings:
        return "coverage"
    return "evaluation"


def run_decision_trace(
    authority: MechanicsAuthority,
    source: FixtureEnvelope | ReplayInput | TacticalState,
    profile: EvaluationProfile = DEFAULT_EVALUATION_PROFILE,
    unit_value_policy: UnitValuePolicy = DEFAULT_UNIT_VALUE_POLICY,
    *,
    implementation_revision: str | None = None,
) -> DecisionTrace:
    """Evaluate one current decision and emit a replay-complete trace.

    Wall-clock timings are measured by the evaluator only when this trace wrapper
    supplies timing sinks. They are deliberately excluded from output identity.
    """

    fixture_id, state = _coerce_source(source)
    timings: dict[str, int] = {}
    counters: dict[str, int] = {}

    def timing_sink(stage: str, elapsed_ns: int) -> None:
        timings[stage] = timings.get(stage, 0) + elapsed_ns

    def counter_sink(name: str, value: int) -> None:
        counters[name] = value

    result = None
    evaluation_exception: Exception | None = None
    try:
        result = evaluate_decision(
            authority,
            state,
            profile,
            unit_value_policy,
            timing_sink=timing_sink,
            counter_sink=counter_sink,
        )
    except Exception as exc:  # Trace API preserves unexpected evaluation failures.
        evaluation_exception = exc

    normalized = _safe_normalized_state(state)
    input_payload = _input_payload(fixture_id, state, normalized)
    state_payload = _object(input_payload["canonical_state"], "canonical_state")
    actions = _actions_from_state_payload(state_payload)
    action_by_id = {
        str(action.get("action_id")): action
        for action in actions
        if isinstance(action.get("action_id"), str)
    }

    evaluation = result.value if result is not None else None
    engine = _engine_payload(
        authority,
        profile,
        unit_value_policy,
        evaluation,
        implementation_revision,
    )

    problems = tuple(result.problems) if result is not None else ()
    status = result.status if result is not None else None
    generation = {
        "decision_status": status.value
        if status is not None
        else "EVALUATION_EXCEPTION",
        "legal_candidates": list(actions),
        "legal_candidate_count": len(actions),
        "rejected_probe_counts": {},
        "diagnostic_problem_count": len(problems),
        "indeterminate_count": sum(
            problem.code
            in (ErrorCode.EVALUATION_UNSUPPORTED, ErrorCode.MECHANICS_UNSUPPORTED)
            for problem in problems
        ),
        "coverage_diagnostics": [_problem_payload(problem) for problem in problems],
    }

    evaluations: tuple[dict[str, JsonValue], ...] = ()
    selection = None
    failure = None
    if evaluation is not None:
        evaluations = tuple(
            _candidate_trace(candidate, action_by_id.get(candidate.action_id))
            for candidate in evaluation.candidates
        )
        selection = _selection_payload(evaluation)
        counters.setdefault("evaluated_candidate_count", len(evaluation.candidates))
        counters.setdefault(
            "epistemic_ranking_scenario_count",
            len(evaluation.epistemic_scenarios),
        )
        counters.setdefault(
            "outcome_branch_count",
            sum(
                candidate.features.outcome_facts.branch_count
                for candidate in evaluation.candidates
            ),
        )
        counters.setdefault(
            "sample_count",
            sum(
                candidate.features.outcome_facts.sample_count
                for candidate in evaluation.candidates
            ),
        )
    elif result is not None:
        failure = {
            "stage": _failure_stage(result.status, timings),
            "status": result.status.value,
            "problems": [_problem_payload(problem) for problem in result.problems],
        }
    else:
        failure = {
            "stage": "evaluation",
            "status": "EVALUATION_EXCEPTION",
            "problems": [
                {
                    "code": "EVALUATION_EXCEPTION",
                    "message": str(evaluation_exception),
                    "exception_type": type(evaluation_exception).__name__,
                }
            ],
        }

    counters.setdefault("legal_candidate_count", len(actions))
    counters.setdefault("coverage_problem_count", len(problems))
    performance = {
        "stage_timings_ns": dict(sorted(timings.items())),
        "counters": dict(sorted(counters.items())),
    }

    try:
        return DecisionTrace.create(
            input=input_payload,
            engine=engine,
            generation=generation,
            evaluations=evaluations,
            selection=selection,
            failure=failure,
            performance=performance,
        )
    except (TypeError, ValueError) as exc:
        # A non-finite or otherwise unserializable semantic output is itself a
        # structured decision failure, never an opaque JSON exception.
        return DecisionTrace.create(
            input=input_payload,
            engine=engine,
            generation=generation,
            evaluations=(),
            selection=None,
            failure={
                "stage": "trace_serialization",
                "status": "INVALID_NUMERIC_OUTPUT",
                "problems": [
                    {
                        "code": "INVALID_NUMERIC_OUTPUT",
                        "message": str(exc),
                    }
                ],
            },
            performance=performance,
        )


def _profile_from_trace(engine: Mapping[str, JsonValue]) -> EvaluationProfile:
    profile = _object(engine.get("evaluation_profile"), "evaluation_profile")
    weights_data = _object(profile.get("weights"), "evaluation_profile.weights")
    scales_data = _object(profile.get("scales"), "evaluation_profile.scales")
    weights = EvaluationWeights(
        **{
            field.name: float(weights_data[field.name])
            for field in fields(EvaluationWeights)
        }
    )
    scales = EvaluationScales(
        **{
            field.name: float(scales_data[field.name])
            for field in fields(EvaluationScales)
        }
    )
    threshold = profile.get("max_self_death_probability")
    return EvaluationProfile(
        version=_string(profile.get("version"), "evaluation_profile.version"),
        weights=weights,
        scales=scales,
        tail_risk_weight=float(profile["tail_risk_weight"]),
        uncertainty_weight=float(profile["uncertainty_weight"]),
        near_tie_margin=float(profile["near_tie_margin"]),
        max_self_death_probability=None if threshold is None else float(threshold),
    )


def _unit_value_policy_from_trace(engine: Mapping[str, JsonValue]) -> UnitValuePolicy:
    policy = _object(engine.get("unit_value_policy"), "unit_value_policy")
    actor_values_raw = policy.get("actor_values")
    if not isinstance(actor_values_raw, Sequence) or isinstance(
        actor_values_raw, str | bytes | bytearray
    ):
        raise ValueError("unit_value_policy.actor_values must be a sequence")
    actor_values = []
    for item in actor_values_raw:
        if not isinstance(item, Sequence) or isinstance(item, str | bytes | bytearray):
            raise ValueError("unit_value_policy actor value must be a pair")
        pair = tuple(item)
        if len(pair) != 2:
            raise ValueError("unit_value_policy actor value must be a pair")
        actor_values.append((str(pair[0]), float(pair[1])))
    return UnitValuePolicy(
        version=_string(policy.get("version"), "unit_value_policy.version"),
        default_value=float(policy["default_value"]),
        actor_values=tuple(actor_values),
    )


def replay_decision_trace(
    authority: MechanicsAuthority,
    expected: DecisionTrace,
) -> TraceReplayResult:
    """Regenerate a trace from its embedded canonical input and config."""

    state_payload = _object(expected.input.get("canonical_state"), "canonical_state")
    state = TacticalState.from_dict(state_payload)
    profile = _profile_from_trace(expected.engine)
    policy = _unit_value_policy_from_trace(expected.engine)
    fixture_value = expected.input.get("fixture_id")
    replay_source: ReplayInput | TacticalState
    if fixture_value is None:
        replay_source = state
    else:
        replay_source = ReplayInput(
            fixture_id=str(fixture_value),
            state=state,
            state_id=state.state_id,
            information_profile=state.information_profile,
            ruleset_content_fingerprint=state.ruleset.content_fingerprint,
        )
    revision_value = expected.engine.get("implementation_revision")
    revision = revision_value if isinstance(revision_value, str) else None
    actual = run_decision_trace(
        authority,
        replay_source,
        profile,
        policy,
        implementation_revision=revision,
    )
    expected_ranking = (
        tuple(expected.selection.get("ranking", ())) if expected.selection else ()
    )
    actual_ranking = (
        tuple(actual.selection.get("ranking", ())) if actual.selection else ()
    )
    expected_chosen = (
        expected.selection.get("chosen_action_id") if expected.selection else None
    )
    actual_chosen = (
        actual.selection.get("chosen_action_id") if actual.selection else None
    )
    matches = expected.output_fingerprint == actual.output_fingerprint
    return TraceReplayResult(
        matches,
        expected.output_fingerprint,
        actual.output_fingerprint,
        expected_ranking == actual_ranking,
        expected_chosen == actual_chosen,
        actual,
    )


def _evaluation_by_action(trace: DecisionTrace) -> dict[str, dict[str, JsonValue]]:
    result = {}
    for candidate in trace.evaluations:
        action_id = candidate.get("action_id")
        if isinstance(action_id, str):
            result[action_id] = candidate
    return result


def _component_values(candidate: dict[str, JsonValue]) -> dict[str, float]:
    evaluation = candidate.get("evaluation")
    if not isinstance(evaluation, Mapping):
        return {}
    components = evaluation.get("components")
    if not isinstance(components, Sequence) or isinstance(
        components, str | bytes | bytearray
    ):
        return {}
    result = {}
    for component in components:
        if not isinstance(component, Mapping):
            continue
        component_id = component.get("component_id")
        selection_value = component.get("selection_value")
        if isinstance(component_id, str) and isinstance(selection_value, int | float):
            result[component_id] = float(selection_value)
    tail_risk = evaluation.get("tail_risk")
    if isinstance(tail_risk, Mapping):
        value = tail_risk.get("selection_penalty")
        if isinstance(value, int | float):
            result["tail_risk_penalty"] = -float(value)
    uncertainty = evaluation.get("uncertainty_penalty")
    if isinstance(uncertainty, int | float):
        result["uncertainty_robustness_adjustment"] = -float(uncertainty)
    return result


def compare_traces(before: DecisionTrace, after: DecisionTrace) -> TraceDiff:
    """Return candidate, rank, and scoring-component deltas between traces."""

    before_by_action = _evaluation_by_action(before)
    after_by_action = _evaluation_by_action(after)
    before_ids = set(before_by_action)
    after_ids = set(after_by_action)
    added = tuple(sorted(after_ids - before_ids))
    removed = tuple(sorted(before_ids - after_ids))

    before_ranking = (
        tuple(before.selection.get("ranking", ())) if before.selection else ()
    )
    after_ranking = tuple(after.selection.get("ranking", ())) if after.selection else ()
    before_rank = {
        str(action_id): rank for rank, action_id in enumerate(before_ranking)
    }
    after_rank = {str(action_id): rank for rank, action_id in enumerate(after_ranking)}
    rank_deltas = tuple(
        RankDelta(action_id, before_rank.get(action_id), after_rank.get(action_id))
        for action_id in sorted(before_ids | after_ids)
        if before_rank.get(action_id) != after_rank.get(action_id)
    )

    component_deltas = []
    for action_id in sorted(before_ids & after_ids):
        left = _component_values(before_by_action[action_id])
        right = _component_values(after_by_action[action_id])
        for component_id in sorted(set(left) | set(right)):
            before_value = left.get(component_id, 0.0)
            after_value = right.get(component_id, 0.0)
            delta = after_value - before_value
            if abs(delta) > 1e-12:
                component_deltas.append(
                    ComponentDelta(
                        action_id,
                        component_id,
                        before_value,
                        after_value,
                        delta,
                    )
                )

    before_chosen = (
        before.selection.get("chosen_action_id") if before.selection else None
    )
    after_chosen = after.selection.get("chosen_action_id") if after.selection else None
    return TraceDiff(
        before_chosen != after_chosen,
        before.output_fingerprint != after.output_fingerprint,
        added,
        removed,
        rank_deltas,
        tuple(component_deltas),
    )
