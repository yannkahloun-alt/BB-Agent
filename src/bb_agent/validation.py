"""Generic M1 fixture expectation and validation harness."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from statistics import median
from typing import Any

from bb_agent.evaluator import (
    DEFAULT_EVALUATION_PROFILE,
    DEFAULT_UNIT_VALUE_POLICY,
    EvaluationProfile,
    UnitValuePolicy,
)
from bb_agent.fixtures import FixtureEnvelope, FixtureSeverity, ReviewStatus
from bb_agent.mechanics import MechanicsAuthority
from bb_agent.serialization import JsonValue, canonical_json_bytes
from bb_agent.trace import (
    DecisionTrace,
    TraceDiff,
    compare_traces,
    replay_decision_trace,
    run_decision_trace,
)

EXPECTATION_VERSION = "m1-fixture-expectations.v1"
HARNESS_VERSION = "m1-validation-harness.v1"
_TOLERANCE = 1e-9


class AssertionStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"


class RelationOperator(StrEnum):
    LT = "<"
    LE = "<="
    EQ = "=="
    NE = "!="
    GE = ">="
    GT = ">"


class RegressionKind(StrEnum):
    NO_CHANGE = "NO_CHANGE"
    HARD_GATED_FAILURE = "HARD_GATED_FAILURE"
    INTENDED_MODEL_VERSION_CHANGE = "INTENDED_MODEL_VERSION_CHANGE"
    CALIBRATION_REVIEW_REQUIRED = "CALIBRATION_REVIEW_REQUIRED"
    ACCEPTABLE_SET_SUBSTITUTION = "ACCEPTABLE_SET_SUBSTITUTION"
    REVIEW_REQUIRED_CHANGE = "REVIEW_REQUIRED_CHANGE"


@dataclass(frozen=True, slots=True)
class TopKExpectation:
    any_of: tuple[str, ...]
    k: int

    def __post_init__(self) -> None:
        if not self.any_of or any(not action_id for action_id in self.any_of):
            raise ValueError("top-K expectation requires action IDs")
        if self.k <= 0:
            raise ValueError("top-K expectation k must be positive")


@dataclass(frozen=True, slots=True)
class NearTieExpectation:
    action_ids: tuple[str, ...]
    expected: bool = True

    def __post_init__(self) -> None:
        if len(self.action_ids) < 2 or any(not item for item in self.action_ids):
            raise ValueError("near-tie expectation requires at least two action IDs")


@dataclass(frozen=True, slots=True)
class MetricRef:
    action_id: str
    path: str

    def __post_init__(self) -> None:
        if not self.action_id or not self.path:
            raise ValueError("metric reference requires action_id and path")


@dataclass(frozen=True, slots=True)
class NumericRelation:
    left: MetricRef
    operator: RelationOperator
    right: MetricRef | None = None
    right_value: float | None = None
    tolerance: float = _TOLERANCE

    def __post_init__(self) -> None:
        if (self.right is None) == (self.right_value is None):
            raise ValueError("numeric relation requires exactly one right operand")
        if self.right_value is not None and not math.isfinite(self.right_value):
            raise ValueError("numeric relation constant must be finite")
        if not math.isfinite(self.tolerance) or self.tolerance < 0:
            raise ValueError(
                "numeric relation tolerance must be finite and nonnegative"
            )


@dataclass(frozen=True, slots=True)
class ActionFactExpectation:
    action_id: str
    path: str
    expected: JsonValue

    def __post_init__(self) -> None:
        if not self.action_id or not self.path:
            raise ValueError("action fact expectation requires action_id and path")
        canonical_json_bytes(self.expected)


@dataclass(frozen=True, slots=True)
class ExplanationExpectation:
    action_id: str
    component_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.action_id or not self.component_ids:
            raise ValueError(
                "explanation expectation requires action and component IDs"
            )
        if any(not item for item in self.component_ids):
            raise ValueError("explanation component IDs must be nonempty")


@dataclass(frozen=True, slots=True)
class FixtureExpectations:
    version: str = EXPECTATION_VERSION
    expected_status: str | None = None
    acceptable_top1: tuple[str, ...] = ()
    forbidden_top1: tuple[str, ...] = ()
    required_orderings: tuple[tuple[str, str], ...] = ()
    top_k: tuple[TopKExpectation, ...] = ()
    near_ties: tuple[NearTieExpectation, ...] = ()
    numeric_relations: tuple[NumericRelation, ...] = ()
    information_sensitive: bool | None = None
    required_explanations: tuple[ExplanationExpectation, ...] = ()
    required_legal_action_ids: tuple[str, ...] = ()
    forbidden_legal_action_ids: tuple[str, ...] = ()
    exact_legal_action_ids: tuple[str, ...] | None = None
    action_facts: tuple[ActionFactExpectation, ...] = ()
    expected_problem_codes: tuple[str, ...] = ()
    expected_mechanic_ids: tuple[str, ...] = ()
    expected_output_fingerprint: str | None = None
    assert_oracle_affordance_set: bool = False
    allow_model_version_change: bool = False

    def __post_init__(self) -> None:
        if self.version != EXPECTATION_VERSION:
            raise ValueError("unsupported fixture expectation version")
        for name, values in (
            ("acceptable_top1", self.acceptable_top1),
            ("forbidden_top1", self.forbidden_top1),
            ("required_legal_action_ids", self.required_legal_action_ids),
            ("forbidden_legal_action_ids", self.forbidden_legal_action_ids),
            ("expected_problem_codes", self.expected_problem_codes),
            ("expected_mechanic_ids", self.expected_mechanic_ids),
        ):
            if any(not item for item in values):
                raise ValueError(f"{name} contains an empty value")
        if self.exact_legal_action_ids is not None and any(
            not item for item in self.exact_legal_action_ids
        ):
            raise ValueError("exact_legal_action_ids contains an empty action ID")
        for pair in self.required_orderings:
            if len(pair) != 2 or not pair[0] or not pair[1] or pair[0] == pair[1]:
                raise ValueError(
                    "required_orderings must contain distinct action pairs"
                )
        if (
            self.expected_output_fingerprint is not None
            and not self.expected_output_fingerprint
        ):
            raise ValueError("expected_output_fingerprint cannot be empty")
        if self.has_ranking_assertions and self.expected_status not in (
            None,
            "SUCCESS",
        ):
            raise ValueError(
                "ranking assertions cannot be combined with a non-success "
                "expected status"
            )

    @property
    def has_ranking_assertions(self) -> bool:
        return bool(
            self.acceptable_top1
            or self.forbidden_top1
            or self.required_orderings
            or self.top_k
            or self.near_ties
            or self.numeric_relations
            or self.information_sensitive is not None
            or self.required_explanations
        )

    @classmethod
    def from_json(cls, value: JsonValue) -> FixtureExpectations:
        data = _expectation_mapping(value, "expectations")
        allowed = {
            "version",
            "expected_status",
            "acceptable_top1",
            "forbidden_top1",
            "required_orderings",
            "top_k",
            "near_ties",
            "numeric_relations",
            "information_sensitive",
            "required_explanations",
            "required_legal_action_ids",
            "forbidden_legal_action_ids",
            "exact_legal_action_ids",
            "action_facts",
            "expected_problem_codes",
            "expected_mechanic_ids",
            "expected_output_fingerprint",
            "assert_oracle_affordance_set",
            "allow_model_version_change",
        }
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(f"unknown fixture expectation fields: {sorted(unknown)}")
        version = _optional_string(data.get("version")) or EXPECTATION_VERSION
        expected_status = _optional_string(data.get("expected_status"))
        acceptable_top1 = _string_tuple(data.get("acceptable_top1"))
        forbidden_top1 = _string_tuple(data.get("forbidden_top1"))
        required_orderings = tuple(
            _action_pair(item, "required_orderings")
            for item in _optional_sequence(data.get("required_orderings"))
        )
        top_k = tuple(_top_k(item) for item in _optional_sequence(data.get("top_k")))
        near_ties = tuple(
            _near_tie(item) for item in _optional_sequence(data.get("near_ties"))
        )
        numeric_relations = tuple(
            _numeric_relation(item)
            for item in _optional_sequence(data.get("numeric_relations"))
        )
        information_sensitive = _optional_bool(data.get("information_sensitive"))
        required_explanations = tuple(
            _explanation_expectation(item)
            for item in _optional_sequence(data.get("required_explanations"))
        )
        required_legal = _string_tuple(data.get("required_legal_action_ids"))
        forbidden_legal = _string_tuple(data.get("forbidden_legal_action_ids"))
        exact_raw = data.get("exact_legal_action_ids")
        exact_legal = None if exact_raw is None else _string_tuple(exact_raw)
        action_facts = tuple(
            _action_fact(item) for item in _optional_sequence(data.get("action_facts"))
        )
        expected_problem_codes = _string_tuple(data.get("expected_problem_codes"))
        expected_mechanic_ids = _string_tuple(data.get("expected_mechanic_ids"))
        expected_output_fingerprint = _optional_string(
            data.get("expected_output_fingerprint")
        )
        return cls(
            version=version,
            expected_status=expected_status,
            acceptable_top1=acceptable_top1,
            forbidden_top1=forbidden_top1,
            required_orderings=required_orderings,
            top_k=top_k,
            near_ties=near_ties,
            numeric_relations=numeric_relations,
            information_sensitive=information_sensitive,
            required_explanations=required_explanations,
            required_legal_action_ids=required_legal,
            forbidden_legal_action_ids=forbidden_legal,
            exact_legal_action_ids=exact_legal,
            action_facts=action_facts,
            expected_problem_codes=expected_problem_codes,
            expected_mechanic_ids=expected_mechanic_ids,
            expected_output_fingerprint=expected_output_fingerprint,
            assert_oracle_affordance_set=(
                _optional_bool(data.get("assert_oracle_affordance_set")) or False
            ),
            allow_model_version_change=(
                _optional_bool(data.get("allow_model_version_change")) or False
            ),
        )


@dataclass(frozen=True, slots=True)
class ValidationAssertion:
    assertion_id: str
    status: AssertionStatus
    gated: bool
    message: str

    @property
    def passed(self) -> bool:
        return self.status is AssertionStatus.PASS


@dataclass(frozen=True, slots=True)
class FixtureValidationReport:
    harness_version: str
    fixture_id: str
    severity: str
    taxonomy: tuple[str, ...]
    trace: DecisionTrace | None
    assertions: tuple[ValidationAssertion, ...]

    @property
    def blocking_failures(self) -> tuple[ValidationAssertion, ...]:
        return tuple(
            item
            for item in self.assertions
            if item.gated and item.status is AssertionStatus.FAIL
        )

    @property
    def review_findings(self) -> tuple[ValidationAssertion, ...]:
        return tuple(
            item for item in self.assertions if item.status is AssertionStatus.REVIEW
        )

    @property
    def passed(self) -> bool:
        return not self.blocking_failures


@dataclass(frozen=True, slots=True)
class CorpusCoverageSummary:
    total_fixtures: int
    gated_fixtures: int
    calibration_fixtures: int
    safety_critical_fixtures: int
    blocking_failure_count: int
    review_finding_count: int
    taxonomy_counts: tuple[tuple[str, int], ...]
    severity_counts: tuple[tuple[str, int], ...]
    information_profile_counts: tuple[tuple[str, int], ...]
    review_status_counts: tuple[tuple[str, int], ...]
    median_decision_ns: int | None
    p95_decision_ns: int | None
    max_decision_ns: int | None


@dataclass(frozen=True, slots=True)
class CorpusValidationReport:
    harness_version: str
    fixtures: tuple[FixtureValidationReport, ...]
    coverage: CorpusCoverageSummary

    @property
    def passed(self) -> bool:
        return self.coverage.blocking_failure_count == 0


@dataclass(frozen=True, slots=True)
class RegressionReport:
    kind: RegressionKind
    diff: TraceDiff
    message: str


def run_fixture_validation(
    authority: MechanicsAuthority,
    fixture: FixtureEnvelope,
    profile: EvaluationProfile = DEFAULT_EVALUATION_PROFILE,
    unit_value_policy: UnitValuePolicy = DEFAULT_UNIT_VALUE_POLICY,
) -> FixtureValidationReport:
    """Validate one fixture and its generic expectation payload."""

    fixture_id = fixture.metadata.fixture_id
    severity = fixture.metadata.severity.value
    taxonomy = fixture.metadata.taxonomy
    assertions: list[ValidationAssertion] = []

    try:
        normalized = fixture.normalized()
    except (TypeError, ValueError, KeyError) as exc:
        assertions.append(
            _hard_assertion("fixture_integrity", False, f"fixture invalid: {exc}")
        )
        return FixtureValidationReport(
            HARNESS_VERSION,
            fixture_id,
            severity,
            taxonomy,
            None,
            tuple(assertions),
        )

    try:
        expectations = (
            None
            if normalized.expectations is None
            else FixtureExpectations.from_json(normalized.expectations)
        )
        if (
            expectations is not None
            and normalized.metadata.expectation_version is not None
            and normalized.metadata.expectation_version != expectations.version
        ):
            raise ValueError(
                "metadata expectation_version does not match expectation payload"
            )
    except (TypeError, ValueError, KeyError) as exc:
        assertions.append(
            _hard_assertion(
                "expectation_schema",
                False,
                f"fixture expectations invalid: {exc}",
            )
        )
        return FixtureValidationReport(
            HARNESS_VERSION,
            fixture_id,
            severity,
            taxonomy,
            None,
            tuple(assertions),
        )

    if (
        normalized.metadata.review_status is ReviewStatus.PROMOTED
        and expectations is None
    ):
        assertions.append(
            _hard_assertion(
                "promoted_expectations",
                False,
                "PROMOTED fixture requires an expectation payload",
            )
        )

    trace = run_decision_trace(authority, normalized, profile, unit_value_policy)
    state_action_ids = tuple(
        action.action_id for action in normalized.state.action_affordances.actions
    )
    trace_action_ids = tuple(sorted(_legal_action_records(trace)))
    assertions.extend(
        (
            _hard_assertion(
                "state_identity",
                trace.input.get("state_id") == normalized.state.state_id,
                "trace state identity matches canonical fixture state",
            ),
            _hard_assertion(
                "affordance_integrity",
                trace_action_ids == tuple(sorted(state_action_ids)),
                "trace legal candidates exactly match the complete fixture "
                "affordance set",
            ),
        )
    )

    try:
        replay = replay_decision_trace(authority, trace)
        replay_ok = (
            replay.matches and replay.ranking_matches and replay.chosen_action_matches
        )
        replay_message = "exact replay reproduced fingerprint/ranking/chosen action"
    except (TypeError, ValueError, KeyError) as exc:
        replay_ok = False
        replay_message = f"replay failed: {exc}"
    assertions.append(_hard_assertion("exact_replay", replay_ok, replay_message))

    if expectations is None:
        if normalized.metadata.review_status is not ReviewStatus.PROMOTED:
            assertions.append(
                ValidationAssertion(
                    "expectations_present",
                    AssertionStatus.REVIEW,
                    False,
                    "fixture has no semantic expectations yet",
                )
            )
    else:
        assertions.extend(_evaluate_expectations(normalized, expectations, trace))

    return FixtureValidationReport(
        HARNESS_VERSION,
        fixture_id,
        severity,
        taxonomy,
        trace,
        tuple(assertions),
    )


def run_validation_corpus(
    authority: MechanicsAuthority,
    fixtures: Sequence[FixtureEnvelope],
    profile: EvaluationProfile = DEFAULT_EVALUATION_PROFILE,
    unit_value_policy: UnitValuePolicy = DEFAULT_UNIT_VALUE_POLICY,
) -> CorpusValidationReport:
    """Run the generic harness and summarize gating/taxonomy/performance coverage."""

    reports = tuple(
        run_fixture_validation(authority, fixture, profile, unit_value_policy)
        for fixture in fixtures
    )
    taxonomy = Counter(tag for fixture in fixtures for tag in fixture.metadata.taxonomy)
    severities = Counter(fixture.metadata.severity.value for fixture in fixtures)
    profiles = Counter(
        fixture.metadata.information_profile.value for fixture in fixtures
    )
    review_statuses = Counter(
        fixture.metadata.review_status.value for fixture in fixtures
    )
    durations = sorted(
        duration
        for report in reports
        if report.trace is not None
        for duration in [_trace_duration_ns(report.trace)]
        if duration is not None
    )
    coverage = CorpusCoverageSummary(
        total_fixtures=len(fixtures),
        gated_fixtures=sum(
            fixture.metadata.severity is not FixtureSeverity.CALIBRATION
            for fixture in fixtures
        ),
        calibration_fixtures=sum(
            fixture.metadata.severity is FixtureSeverity.CALIBRATION
            for fixture in fixtures
        ),
        safety_critical_fixtures=sum(
            fixture.metadata.severity is FixtureSeverity.SAFETY_CRITICAL
            for fixture in fixtures
        ),
        blocking_failure_count=sum(len(report.blocking_failures) for report in reports),
        review_finding_count=sum(len(report.review_findings) for report in reports),
        taxonomy_counts=tuple(sorted(taxonomy.items())),
        severity_counts=tuple(sorted(severities.items())),
        information_profile_counts=tuple(sorted(profiles.items())),
        review_status_counts=tuple(sorted(review_statuses.items())),
        median_decision_ns=None if not durations else int(median(durations)),
        p95_decision_ns=(
            None
            if not durations
            else durations[max(0, math.ceil(len(durations) * 0.95) - 1)]
        ),
        max_decision_ns=None if not durations else durations[-1],
    )
    return CorpusValidationReport(HARNESS_VERSION, reports, coverage)


def classify_trace_change(
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

    before_status = str(before.generation.get("decision_status") or "")
    after_status = str(after.generation.get("decision_status") or "")
    expected_status = None if expectations is None else expectations.expected_status
    if after_status != "SUCCESS" and after_status != expected_status:
        return RegressionReport(
            RegressionKind.HARD_GATED_FAILURE,
            diff,
            (
                "unexpected decision failure/coverage status introduced: "
                f"{before_status!r} -> {after_status!r}"
            ),
        )

    missing_evaluations = tuple(
        sorted(set(_candidate_records(before)) - set(_candidate_records(after)))
    )
    if after_status == "SUCCESS" and missing_evaluations:
        return RegressionReport(
            RegressionKind.HARD_GATED_FAILURE,
            diff,
            "successful decision stopped evaluating legal candidates: "
            + ", ".join(missing_evaluations),
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


def _evaluate_expectations(
    fixture: FixtureEnvelope,
    expectations: FixtureExpectations,
    trace: DecisionTrace,
) -> list[ValidationAssertion]:
    results: list[ValidationAssertion] = []
    tactical_gate = fixture.metadata.severity is not FixtureSeverity.CALIBRATION
    actual_status = str(trace.generation.get("decision_status") or "")
    legal_records = _legal_action_records(trace)
    legal_ids = set(legal_records)
    problems = _trace_problems(trace)
    problem_codes = {
        str(problem.get("code"))
        for problem in problems
        if problem.get("code") is not None
    }
    mechanic_ids = {
        str(problem.get("mechanic_id"))
        for problem in problems
        if problem.get("mechanic_id") is not None
    }

    if expectations.expected_status is not None:
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

    if expectations.exact_legal_action_ids is not None:
        expected = set(expectations.exact_legal_action_ids)
        results.append(
            _hard_assertion(
                "exact_legal_action_ids",
                legal_ids == expected,
                f"legal action IDs are {sorted(legal_ids)}; expected "
                f"{sorted(expected)}",
            )
        )
    for action_id in expectations.required_legal_action_ids:
        results.append(
            _hard_assertion(
                f"legal:{action_id}",
                action_id in legal_ids,
                f"required legal action {action_id!r} is present",
            )
        )
    for action_id in expectations.forbidden_legal_action_ids:
        results.append(
            _hard_assertion(
                f"illegal:{action_id}",
                action_id not in legal_ids,
                f"forbidden legal action {action_id!r} is absent",
            )
        )

    for fact in expectations.action_facts:
        action = legal_records.get(fact.action_id)
        try:
            actual = None if action is None else _lookup_path(action, fact.path)
            passed = action is not None and actual == fact.expected
        except (IndexError, KeyError, TypeError, ValueError):
            actual = None
            passed = False
        results.append(
            _hard_assertion(
                f"action_fact:{fact.action_id}:{fact.path}",
                passed,
                (
                    f"action {fact.action_id!r} field {fact.path!r} "
                    f"is {actual!r}; expected {fact.expected!r}"
                ),
            )
        )

    for code in expectations.expected_problem_codes:
        results.append(
            _hard_assertion(
                f"problem_code:{code}",
                code in problem_codes,
                f"expected problem code {code!r} is present",
            )
        )
    for mechanic_id in expectations.expected_mechanic_ids:
        results.append(
            _hard_assertion(
                f"mechanic_id:{mechanic_id}",
                mechanic_id in mechanic_ids,
                f"expected mechanic ID {mechanic_id!r} is present",
            )
        )

    if expectations.assert_oracle_affordance_set:
        oracle = fixture.oracle_annotations
        oracle_mapping = oracle if isinstance(oracle, Mapping) else None
        oracle_complete = (
            oracle_mapping is not None
            and oracle_mapping.get("affordance_set_complete") is True
        )
        oracle_ids_value = (
            None if oracle_mapping is None else oracle_mapping.get("legal_action_ids")
        )
        oracle_ids = _string_set_or_none(oracle_ids_value)
        results.append(
            _hard_assertion(
                "oracle_affordance_metadata",
                oracle_complete and oracle_ids is not None,
                "oracle annotations declare complete legal_action_ids",
            )
        )
        if oracle_ids is not None:
            results.append(
                _hard_assertion(
                    "oracle_affordance_exact",
                    legal_ids == oracle_ids,
                    (
                        f"fixture/trace legal IDs {sorted(legal_ids)} "
                        f"match oracle IDs {sorted(oracle_ids)}"
                    ),
                )
            )

    chosen = _chosen_action(trace)
    ranking = _ranking(trace)
    if expectations.acceptable_top1:
        results.append(
            _policy_assertion(
                "acceptable_top1",
                chosen in set(expectations.acceptable_top1),
                tactical_gate,
                (
                    f"chosen action {chosen!r} is in acceptable_top1 "
                    f"{list(expectations.acceptable_top1)!r}"
                ),
            )
        )
    if expectations.forbidden_top1:
        results.append(
            _policy_assertion(
                "forbidden_top1",
                chosen not in set(expectations.forbidden_top1),
                tactical_gate,
                (
                    f"chosen action {chosen!r} is not forbidden_top1 "
                    f"{list(expectations.forbidden_top1)!r}"
                ),
            )
        )

    rank_index = {action_id: index for index, action_id in enumerate(ranking)}
    for higher, lower in expectations.required_orderings:
        higher_id = _resolve_action_token(higher, trace)
        lower_id = _resolve_action_token(lower, trace)
        passed = (
            higher_id in rank_index
            and lower_id in rank_index
            and rank_index[higher_id] < rank_index[lower_id]
        )
        results.append(
            _policy_assertion(
                f"ordering:{higher}>{lower}",
                passed,
                tactical_gate,
                f"required ordering {higher!r} > {lower!r}",
            )
        )

    for index, rule in enumerate(expectations.top_k):
        resolved = {
            resolved
            for item in rule.any_of
            if (resolved := _resolve_action_token(item, trace)) is not None
        }
        passed = bool(resolved.intersection(ranking[: rule.k]))
        results.append(
            _policy_assertion(
                f"top_k:{index}",
                passed,
                tactical_gate,
                f"one of {sorted(resolved)} appears in top {rule.k}",
            )
        )

    near_groups = _near_tie_groups(trace)
    for index, rule in enumerate(expectations.near_ties):
        resolved = tuple(_resolve_action_token(item, trace) for item in rule.action_ids)
        complete = all(item is not None for item in resolved)
        resolved_set = {item for item in resolved if item is not None}
        actual_near = complete and any(
            resolved_set.issubset(group) for group in near_groups
        )
        results.append(
            _policy_assertion(
                f"near_tie:{index}",
                complete and actual_near is rule.expected,
                tactical_gate,
                f"near-tie expectation for {rule.action_ids!r} is {rule.expected}",
            )
        )

    for index, relation in enumerate(expectations.numeric_relations):
        try:
            left = _metric_value(trace, relation.left)
            right = (
                relation.right_value
                if relation.right is None
                else _metric_value(trace, relation.right)
            )
            assert right is not None
            passed = _compare_numeric(
                left, relation.operator, right, relation.tolerance
            )
            message = f"numeric relation {left} {relation.operator.value} {right}"
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            passed = False
            message = f"numeric relation could not resolve: {exc}"
        results.append(
            _policy_assertion(
                f"numeric_relation:{index}",
                passed,
                tactical_gate,
                message,
            )
        )

    if expectations.information_sensitive is not None:
        actual = (
            None
            if trace.selection is None
            else trace.selection.get("information_sensitive")
        )
        results.append(
            _policy_assertion(
                "information_sensitive",
                actual is expectations.information_sensitive,
                tactical_gate,
                (
                    f"decision information_sensitive is {actual!r}; "
                    f"expected {expectations.information_sensitive!r}"
                ),
            )
        )

    candidates = _candidate_records(trace)
    for index, rule in enumerate(expectations.required_explanations):
        action_id = _resolve_action_token(rule.action_id, trace)
        record = None if action_id is None else candidates.get(action_id)
        component_ids = _explanation_component_ids(record)
        missing = set(rule.component_ids) - component_ids
        results.append(
            _policy_assertion(
                f"explanation_components:{index}",
                not missing,
                tactical_gate,
                (
                    f"action {action_id!r} explanation contains "
                    f"{list(rule.component_ids)!r}; missing {sorted(missing)!r}"
                ),
            )
        )

    if expectations.expected_output_fingerprint is not None:
        results.append(
            _hard_assertion(
                "output_fingerprint",
                trace.output_fingerprint == expectations.expected_output_fingerprint,
                (
                    f"output fingerprint is {trace.output_fingerprint}; expected "
                    f"{expectations.expected_output_fingerprint}"
                ),
            )
        )
    return results


def _hard_assertion(
    assertion_id: str,
    passed: bool,
    message: str,
) -> ValidationAssertion:
    return ValidationAssertion(
        assertion_id,
        AssertionStatus.PASS if passed else AssertionStatus.FAIL,
        True,
        message,
    )


def _policy_assertion(
    assertion_id: str,
    passed: bool,
    gated: bool,
    message: str,
) -> ValidationAssertion:
    if passed:
        status = AssertionStatus.PASS
    elif gated:
        status = AssertionStatus.FAIL
    else:
        status = AssertionStatus.REVIEW
    return ValidationAssertion(assertion_id, status, gated, message)


def _expectation_mapping(value: JsonValue, name: str) -> dict[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    result: dict[str, JsonValue] = {}
    for key, child in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{name} keys must be strings")
        result[key] = child
    return result


def _optional_sequence(value: JsonValue) -> tuple[JsonValue, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        raise ValueError("expectation value must be an array")
    return tuple(value)


def _optional_string(value: JsonValue) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError("expectation value must be a nonempty string")
    return value


def _optional_bool(value: JsonValue) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError("expectation value must be boolean")
    return value


def _string_tuple(value: JsonValue) -> tuple[str, ...]:
    result = []
    for item in _optional_sequence(value):
        if not isinstance(item, str) or not item:
            raise ValueError("expectation array must contain nonempty strings")
        result.append(item)
    return tuple(result)


def _string_set_or_none(value: JsonValue) -> set[str] | None:
    if value is None:
        return None
    try:
        return set(_string_tuple(value))
    except ValueError:
        return None


def _action_pair(value: JsonValue, name: str) -> tuple[str, str]:
    items = _optional_sequence(value)
    if len(items) != 2 or any(not isinstance(item, str) or not item for item in items):
        raise ValueError(f"{name} entries must be two action IDs")
    return str(items[0]), str(items[1])


def _top_k(value: JsonValue) -> TopKExpectation:
    data = _expectation_mapping(value, "top_k")
    if set(data) != {"any_of", "k"}:
        raise ValueError("top_k entries require exactly any_of and k")
    k = data["k"]
    if isinstance(k, bool) or not isinstance(k, int):
        raise ValueError("top_k k must be an integer")
    return TopKExpectation(_string_tuple(data["any_of"]), k)


def _near_tie(value: JsonValue) -> NearTieExpectation:
    data = _expectation_mapping(value, "near_ties")
    if set(data) - {"action_ids", "expected"} or "action_ids" not in data:
        raise ValueError("near_tie entries require action_ids and optional expected")
    expected = _optional_bool(data.get("expected"))
    return NearTieExpectation(
        _string_tuple(data["action_ids"]),
        True if expected is None else expected,
    )


def _metric_ref(value: JsonValue) -> MetricRef:
    data = _expectation_mapping(value, "metric reference")
    if set(data) != {"action_id", "path"}:
        raise ValueError("metric reference requires action_id and path")
    return MetricRef(
        _optional_string(data["action_id"]) or "",
        _optional_string(data["path"]) or "",
    )


def _numeric_relation(value: JsonValue) -> NumericRelation:
    data = _expectation_mapping(value, "numeric relation")
    allowed = {"left", "op", "right", "right_value", "tolerance"}
    if set(data) - allowed or "left" not in data or "op" not in data:
        raise ValueError("numeric relation fields are invalid")
    right = None if data.get("right") is None else _metric_ref(data["right"])
    right_value_raw = data.get("right_value")
    right_value: float | None
    if right_value_raw is None:
        right_value = None
    elif isinstance(right_value_raw, bool) or not isinstance(
        right_value_raw, int | float
    ):
        raise ValueError("numeric relation right_value must be numeric")
    else:
        right_value = float(right_value_raw)
    tolerance_raw = data.get("tolerance")
    if tolerance_raw is None:
        tolerance = _TOLERANCE
    elif isinstance(tolerance_raw, bool) or not isinstance(tolerance_raw, int | float):
        raise ValueError("numeric relation tolerance must be numeric")
    else:
        tolerance = float(tolerance_raw)
    return NumericRelation(
        left=_metric_ref(data["left"]),
        operator=RelationOperator(_optional_string(data["op"]) or ""),
        right=right,
        right_value=right_value,
        tolerance=tolerance,
    )


def _action_fact(value: JsonValue) -> ActionFactExpectation:
    data = _expectation_mapping(value, "action fact")
    if set(data) != {"action_id", "path", "equals"}:
        raise ValueError("action fact requires action_id, path and equals")
    return ActionFactExpectation(
        _optional_string(data["action_id"]) or "",
        _optional_string(data["path"]) or "",
        data["equals"],
    )


def _explanation_expectation(value: JsonValue) -> ExplanationExpectation:
    data = _expectation_mapping(value, "required_explanations")
    if set(data) != {"action_id", "component_ids"}:
        raise ValueError("explanation expectation requires action_id and component_ids")
    return ExplanationExpectation(
        _optional_string(data["action_id"]) or "",
        _string_tuple(data["component_ids"]),
    )


def _legal_action_records(trace: DecisionTrace) -> dict[str, Mapping[str, Any]]:
    actions = trace.generation.get("legal_candidates")
    result: dict[str, Mapping[str, Any]] = {}
    if not isinstance(actions, Sequence) or isinstance(
        actions, str | bytes | bytearray
    ):
        return result
    for action in actions:
        if not isinstance(action, Mapping):
            continue
        action_id = action.get("action_id")
        if isinstance(action_id, str):
            result[action_id] = action
    return result


def _candidate_records(trace: DecisionTrace) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for record in trace.evaluations:
        action_id = record.get("action_id")
        if isinstance(action_id, str):
            result[action_id] = record
    return result


def _trace_problems(trace: DecisionTrace) -> tuple[Mapping[str, Any], ...]:
    result: list[Mapping[str, Any]] = []
    for source in (
        trace.generation.get("coverage_diagnostics"),
        None if trace.failure is None else trace.failure.get("problems"),
    ):
        if not isinstance(source, Sequence) or isinstance(
            source, str | bytes | bytearray
        ):
            continue
        result.extend(item for item in source if isinstance(item, Mapping))
    return tuple(result)


def _chosen_action(trace: DecisionTrace) -> str | None:
    if trace.selection is None:
        return None
    value = trace.selection.get("chosen_action_id")
    return value if isinstance(value, str) else None


def _ranking(trace: DecisionTrace) -> tuple[str, ...]:
    if trace.selection is None:
        return ()
    value = trace.selection.get("ranking")
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _near_tie_groups(trace: DecisionTrace) -> tuple[set[str], ...]:
    if trace.selection is None:
        return ()
    raw = trace.selection.get("near_ties")
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes | bytearray):
        return ()
    groups = []
    for group in raw:
        if isinstance(group, Sequence) and not isinstance(
            group, str | bytes | bytearray
        ):
            groups.append({item for item in group if isinstance(item, str)})
    return tuple(groups)


def _resolve_action_token(token: str, trace: DecisionTrace) -> str | None:
    if token in {"$chosen", "$top1"}:
        return _chosen_action(trace)
    if token == "$runner_up":
        ranking = _ranking(trace)
        return ranking[1] if len(ranking) > 1 else None
    return token


def _lookup_path(root: Any, path: str) -> Any:
    current = root
    for segment in path.split("."):
        if isinstance(current, Mapping):
            if segment not in current:
                raise KeyError(segment)
            current = current[segment]
            continue
        if isinstance(current, Sequence) and not isinstance(
            current, str | bytes | bytearray
        ):
            if segment.isdigit():
                current = current[int(segment)]
                continue
            matching = [
                item
                for item in current
                if isinstance(item, Mapping) and item.get("component_id") == segment
            ]
            if len(matching) == 1:
                current = matching[0]
                continue
        raise KeyError(segment)
    return current


def _metric_value(trace: DecisionTrace, ref: MetricRef) -> float:
    action_id = _resolve_action_token(ref.action_id, trace)
    if action_id is None:
        raise KeyError(ref.action_id)
    record = _candidate_records(trace).get(action_id)
    if record is None:
        raise KeyError(action_id)
    value = _lookup_path(record, ref.path)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"metric {ref.path!r} is not numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"metric {ref.path!r} is not finite")
    return numeric


def _compare_numeric(
    left: float,
    operator: RelationOperator,
    right: float,
    tolerance: float,
) -> bool:
    if operator is RelationOperator.EQ:
        return math.isclose(left, right, abs_tol=tolerance)
    if operator is RelationOperator.NE:
        return not math.isclose(left, right, abs_tol=tolerance)
    if operator is RelationOperator.LT:
        return left < right - tolerance
    if operator is RelationOperator.LE:
        return left <= right + tolerance
    if operator is RelationOperator.GT:
        return left > right + tolerance
    if operator is RelationOperator.GE:
        return left >= right - tolerance
    raise AssertionError("unreachable relation operator")


def _explanation_component_ids(record: Mapping[str, Any] | None) -> set[str]:
    if record is None:
        return set()
    evaluation = record.get("evaluation")
    if not isinstance(evaluation, Mapping):
        return set()
    facts = evaluation.get("explanation_facts")
    if not isinstance(facts, Sequence) or isinstance(facts, str | bytes | bytearray):
        return set()
    return {
        str(item.get("component_id"))
        for item in facts
        if isinstance(item, Mapping) and isinstance(item.get("component_id"), str)
    }


def _semantic_component_inventory(trace: DecisionTrace) -> dict[str, set[str]]:
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


def _trace_duration_ns(trace: DecisionTrace) -> int | None:
    timings = trace.performance.get("stage_timings_ns")
    if not isinstance(timings, Mapping):
        return None
    values = [
        value
        for value in timings.values()
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
    ]
    return sum(values) if values else None


def _engine_model_identity(trace: DecisionTrace) -> tuple[tuple[str, bytes], ...]:
    keys = (
        "contract_versions",
        "evaluator_version",
        "evaluation_config_version",
        "evaluation_profile_fingerprint",
        "unit_value_policy_fingerprint",
        "mechanics_manifest_version",
        "mechanics_manifest_fingerprint",
        "declared_outcome_model_version",
        "outcome_model_versions",
        "simulator_settings",
    )
    return tuple((key, canonical_json_bytes(trace.engine.get(key))) for key in keys)
