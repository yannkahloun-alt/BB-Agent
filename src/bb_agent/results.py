"""Stable structured outcomes for validation and mechanics coverage boundaries."""

from dataclasses import dataclass
from enum import StrEnum


class ResultStatus(StrEnum):
    SUCCESS = "SUCCESS"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    INCOMPLETE_COVERAGE = "INCOMPLETE_COVERAGE"


class ErrorCode(StrEnum):
    VALIDATION_FAILED = "VALIDATION_FAILED"
    MECHANICS_UNSUPPORTED = "MECHANICS_UNSUPPORTED"
    EVALUATION_UNSUPPORTED = "EVALUATION_UNSUPPORTED"
    CATALOG_INVALID = "CATALOG_INVALID"
    MANIFEST_INVALID = "MANIFEST_INVALID"
    CATALOG_MISMATCH = "CATALOG_MISMATCH"
    RESOLUTION_STAGE_CONFLICT = "RESOLUTION_STAGE_CONFLICT"
    FIXTURE_IO_FAILED = "FIXTURE_IO_FAILED"
    FIXTURE_JSON_INVALID = "FIXTURE_JSON_INVALID"
    FIXTURE_SCHEMA_UNSUPPORTED = "FIXTURE_SCHEMA_UNSUPPORTED"
    FIXTURE_METADATA_INVALID = "FIXTURE_METADATA_INVALID"
    FIXTURE_STATE_INVALID = "FIXTURE_STATE_INVALID"
    FIXTURE_STATE_HASH_MISMATCH = "FIXTURE_STATE_HASH_MISMATCH"
    FIXTURE_PROFILE_MISMATCH = "FIXTURE_PROFILE_MISMATCH"
    FIXTURE_RULESET_MISMATCH = "FIXTURE_RULESET_MISMATCH"
    FIXTURE_AFFORDANCE_MISMATCH = "FIXTURE_AFFORDANCE_MISMATCH"
    FIXTURE_PAIR_MISMATCH = "FIXTURE_PAIR_MISMATCH"


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
