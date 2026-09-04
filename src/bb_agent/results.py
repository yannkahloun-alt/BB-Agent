"""Stable structured outcomes for validation and mechanics coverage boundaries."""

from dataclasses import dataclass
from enum import StrEnum


class ResultStatus(StrEnum):
    SUCCESS = "SUCCESS"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    INCOMPLETE_COVERAGE = "INCOMPLETE_COVERAGE"


class ErrorCode(StrEnum):
    VALIDATION_FAILED = "VALIDATION_FAILED"
    EVALUATION_UNSUPPORTED = "EVALUATION_UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class Problem:
    code: ErrorCode
    message: str
    path: str | None = None
    mechanic_id: str | None = None


@dataclass(frozen=True, slots=True)
class Result[T]:
    status: ResultStatus
    value: T | None = None
    problems: tuple[Problem, ...] = ()

    def __post_init__(self) -> None:
        if self.status is ResultStatus.SUCCESS:
            if self.problems:
                raise ValueError("successful results cannot contain problems")
        elif not self.problems:
            raise ValueError("failed results must contain at least one problem")

    @classmethod
    def success(cls, value: T) -> "Result[T]":
        return cls(status=ResultStatus.SUCCESS, value=value)

    @classmethod
    def validation_failure(cls, *problems: Problem) -> "Result[T]":
        return cls(status=ResultStatus.VALIDATION_FAILURE, problems=problems)

    @classmethod
    def incomplete_coverage(cls, *problems: Problem) -> "Result[T]":
        return cls(status=ResultStatus.INCOMPLETE_COVERAGE, problems=problems)
