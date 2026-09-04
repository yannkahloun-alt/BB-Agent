import pytest

from bb_agent.results import ErrorCode, Problem, Result, ResultStatus


def test_validation_failure_is_structured_without_raising() -> None:
    problem = Problem(
        code=ErrorCode.VALIDATION_FAILED,
        message="active actor is missing",
        path="$.decision.active_actor_id",
    )

    result = Result[object].validation_failure(problem)

    assert result.status is ResultStatus.VALIDATION_FAILURE
    assert result.problems == (problem,)
    assert result.value is None


def test_incomplete_coverage_identifies_unsupported_mechanic() -> None:
    problem = Problem(
        code=ErrorCode.EVALUATION_UNSUPPORTED,
        message="no declared outcome model",
        mechanic_id="skill.special_attack",
    )

    result = Result[object].incomplete_coverage(problem)

    assert result.status is ResultStatus.INCOMPLETE_COVERAGE
    assert result.problems[0].mechanic_id == "skill.special_attack"


def test_failed_result_requires_a_problem() -> None:
    with pytest.raises(ValueError, match="at least one problem"):
        Result[object](status=ResultStatus.INCOMPLETE_COVERAGE)
