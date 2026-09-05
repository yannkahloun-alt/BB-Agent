"""Canonical current-candidate resolution and narrow evaluation failure boundaries."""

from __future__ import annotations

from dataclasses import dataclass, replace

from bb_agent.mechanics import AffordanceCoverage, CoverageStatus, MechanicsAuthority
from bb_agent.results import ErrorCode, Problem, Result, ResultStatus
from bb_agent.tactical_state import ActionAffordance, TacticalState

CandidateReference = str | ActionAffordance


@dataclass(frozen=True, slots=True)
class CanonicalCandidate:
    """One canonical current action resolved from a validated tactical state."""

    state: TacticalState
    action: ActionAffordance
    structural_coverage: AffordanceCoverage


class EvaluationUnsupported(ValueError):
    """A structurally supported candidate lacks supported evaluation inputs."""

    def __init__(self, message: str, *, path: str, mechanic_id: str) -> None:
        super().__init__(message)
        self.problem = Problem(
            ErrorCode.EVALUATION_UNSUPPORTED, message, path, mechanic_id
        )


class EvaluationUncertaintyUnsupported(EvaluationUnsupported):
    """A candidate cannot represent the current epistemic outcome domain."""


class EvaluationInvalid(ValueError):
    """A candidate/state contradiction violates the canonical input contract."""

    def __init__(self, message: str, *, path: str) -> None:
        super().__init__(message)
        self.problem = Problem(ErrorCode.VALIDATION_FAILED, message, path)


def candidate_action_id(reference: CandidateReference) -> str:
    """Return only command identity from legacy action-object callers.

    Production evaluators resolve all executable fields back from TacticalState.
    An ActionAffordance is accepted only as a compatibility reference; none of its
    AP/FAT/preview/target/mechanics fields are consumed.
    """

    if isinstance(reference, ActionAffordance):
        return reference.action_id
    if isinstance(reference, str) and reference:
        return reference
    raise TypeError(
        "candidate reference must be a nonempty action_id or ActionAffordance"
    )


def resolve_current_candidate(
    authority: MechanicsAuthority,
    state: TacticalState,
    reference: CandidateReference,
) -> Result[CanonicalCandidate]:
    """Resolve one current candidate from normalized state and structural coverage."""

    action_id = candidate_action_id(reference)
    try:
        normalized = state.normalized()
    except (TypeError, ValueError) as exc:
        return Result.validation_failure(
            Problem(ErrorCode.VALIDATION_FAILED, str(exc), "state")
        )

    coverage = authority.classify(normalized)
    if coverage.status is ResultStatus.VALIDATION_FAILURE:
        return Result(ResultStatus.VALIDATION_FAILURE, problems=coverage.problems)
    assert coverage.value is not None

    action = next(
        (
            item
            for item in normalized.action_affordances.actions
            if item.action_id == action_id
        ),
        None,
    )
    if action is None:
        return Result.validation_failure(
            Problem(
                ErrorCode.VALIDATION_FAILED,
                "action_id is not a canonical current action in this state",
                f"action_affordances.{action_id}",
            )
        )

    structural = next(
        item for item in coverage.value.affordances if item.action_id == action_id
    )
    if structural.status is CoverageStatus.EVALUATION_UNSUPPORTED:
        problems = tuple(
            replace(problem, code=ErrorCode.MECHANICS_UNSUPPORTED)
            for problem in structural.problems
        )
        return Result(ResultStatus.INCOMPLETE_COVERAGE, problems=problems)
    return Result.success(CanonicalCandidate(normalized, action, structural))


def evaluation_failure_result[T](
    exc: EvaluationUnsupported | EvaluationInvalid,
) -> Result[T]:
    """Translate only deliberate evaluation failures; programmer errors propagate."""

    if isinstance(exc, EvaluationUnsupported):
        return Result.incomplete_coverage(exc.problem)
    return Result.validation_failure(exc.problem)
