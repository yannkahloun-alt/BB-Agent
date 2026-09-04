"""Versioned, deterministic fixture packages and replay inputs."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from bb_agent.results import ErrorCode, Problem, Result
from bb_agent.serialization import JsonValue, canonical_json_bytes, canonical_sha256
from bb_agent.tactical_state import (
    ActionAffordance,
    ActionAffordanceSet,
    AffordanceCompleteness,
    Combatant,
    EffectState,
    GroundEntity,
    InformationProfile,
    ItemState,
    KnowledgeClass,
    KnownValue,
    Representation,
    SkillState,
    TacticalStat,
    TacticalState,
    TurnEntry,
    TurnState,
)
from bb_agent.versions import CURRENT_VERSIONS


class FixtureSourceKind(StrEnum):
    HANDCRAFTED = "HANDCRAFTED"
    REAL_CAPTURE = "REAL_CAPTURE"
    REDUCED_REGRESSION = "REDUCED_REGRESSION"


class FixtureSeverity(StrEnum):
    CORE = "CORE"
    SAFETY_CRITICAL = "SAFETY_CRITICAL"
    QUALITY = "QUALITY"
    CALIBRATION = "CALIBRATION"


class ReviewStatus(StrEnum):
    DRAFT = "DRAFT"
    REVIEWED = "REVIEWED"
    PROMOTED = "PROMOTED"


@dataclass(frozen=True, slots=True)
class FixtureMetadata:
    fixture_id: str
    source_kind: FixtureSourceKind
    taxonomy: tuple[str, ...]
    severity: FixtureSeverity
    scenario_intent: str
    ruleset_content_fingerprint: str
    information_profile: InformationProfile
    affordance_completeness: AffordanceCompleteness
    expectation_version: str | None = None
    review_status: ReviewStatus = ReviewStatus.DRAFT
    provenance: JsonValue = None

    def __post_init__(self) -> None:
        if not self.fixture_id or not self.scenario_intent:
            raise ValueError("fixture_id and scenario_intent must be nonempty")
        if not self.ruleset_content_fingerprint:
            raise ValueError("ruleset_content_fingerprint must be nonempty")
        if not self.taxonomy or any(not tag for tag in self.taxonomy):
            raise ValueError("fixture taxonomy requires nonempty tags")
        if len(set(self.taxonomy)) != len(self.taxonomy):
            raise ValueError("fixture taxonomy contains duplicate tags")
        for value, expected, name in (
            (self.source_kind, FixtureSourceKind, "source_kind"),
            (self.severity, FixtureSeverity, "severity"),
            (self.information_profile, InformationProfile, "information_profile"),
            (
                self.affordance_completeness,
                AffordanceCompleteness,
                "affordance_completeness",
            ),
            (self.review_status, ReviewStatus, "review_status"),
        ):
            if not isinstance(value, expected):
                raise ValueError(f"fixture metadata {name} is invalid")
        canonical_json_bytes(self.provenance)

    def normalized(self) -> Self:
        return type(self)(
            fixture_id=self.fixture_id,
            source_kind=self.source_kind,
            taxonomy=tuple(sorted(self.taxonomy)),
            severity=self.severity,
            scenario_intent=self.scenario_intent,
            ruleset_content_fingerprint=self.ruleset_content_fingerprint,
            information_profile=self.information_profile,
            affordance_completeness=self.affordance_completeness,
            expectation_version=self.expectation_version,
            review_status=self.review_status,
            provenance=self.provenance,
        )


@dataclass(frozen=True, slots=True)
class ReplayInput:
    """The complete ranking-affecting input available to later decision APIs."""

    fixture_id: str
    state: TacticalState
    state_id: str
    information_profile: InformationProfile
    ruleset_content_fingerprint: str

    def __post_init__(self) -> None:
        if self.state.state_id != self.state_id:
            raise ValueError("replay state_id does not match state")
        if self.state.information_profile is not self.information_profile:
            raise ValueError("replay information profile does not match state")
        if self.state.ruleset.content_fingerprint != self.ruleset_content_fingerprint:
            raise ValueError("replay ruleset fingerprint does not match state")

    @property
    def decision_identity(self) -> str:
        return canonical_sha256(
            {
                "information_profile": self.information_profile.value,
                "ruleset_content_fingerprint": self.ruleset_content_fingerprint,
                "state_id": self.state_id,
            }
        )


@dataclass(frozen=True, slots=True)
class FixtureEnvelope:
    schema_version: str
    metadata: FixtureMetadata
    state: TacticalState
    state_hash: str
    expectations: JsonValue = None
    oracle_annotations: JsonValue = None

    def __post_init__(self) -> None:
        canonical_json_bytes(self.expectations)
        canonical_json_bytes(self.oracle_annotations)

    @classmethod
    def create(
        cls,
        *,
        metadata: FixtureMetadata,
        state: TacticalState,
        expectations: JsonValue = None,
        oracle_annotations: JsonValue = None,
    ) -> Self:
        normalized = state.normalized()
        envelope = cls(
            schema_version=CURRENT_VERSIONS.fixture,
            metadata=metadata.normalized(),
            state=normalized,
            state_hash=normalized.state_id,
            expectations=expectations,
            oracle_annotations=oracle_annotations,
        )
        envelope._validate()
        return envelope

    def normalized(self) -> Self:
        state = self.state.normalized()
        envelope = type(self)(
            schema_version=self.schema_version,
            metadata=self.metadata.normalized(),
            state=state,
            state_hash=self.state_hash,
            expectations=self.expectations,
            oracle_annotations=self.oracle_annotations,
        )
        envelope._validate()
        return envelope

    def _validate(self) -> None:
        if self.schema_version != CURRENT_VERSIONS.fixture:
            raise _FixtureValidation(
                ErrorCode.FIXTURE_SCHEMA_UNSUPPORTED,
                "unsupported fixture schema_version",
                "$.schema_version",
            )
        if self.state_hash != self.state.state_id:
            raise _FixtureValidation(
                ErrorCode.FIXTURE_STATE_HASH_MISMATCH,
                "state_hash does not match normalized tactical state",
                "$.state_hash",
            )
        if self.metadata.information_profile is not self.state.information_profile:
            raise _FixtureValidation(
                ErrorCode.FIXTURE_PROFILE_MISMATCH,
                "fixture metadata profile does not match tactical state",
                "$.metadata.information_profile",
            )
        if (
            self.metadata.ruleset_content_fingerprint
            != self.state.ruleset.content_fingerprint
        ):
            raise _FixtureValidation(
                ErrorCode.FIXTURE_RULESET_MISMATCH,
                "fixture metadata ruleset fingerprint does not match tactical state",
                "$.metadata.ruleset_content_fingerprint",
            )
        if (
            self.metadata.affordance_completeness
            is not self.state.action_affordances.completeness
        ):
            raise _FixtureValidation(
                ErrorCode.FIXTURE_AFFORDANCE_MISMATCH,
                "fixture completeness declaration does not match affordance set",
                "$.metadata.affordance_completeness",
            )
        if self.metadata.affordance_completeness is not AffordanceCompleteness.COMPLETE:
            raise _FixtureValidation(
                ErrorCode.FIXTURE_AFFORDANCE_MISMATCH,
                "M1 replay fixtures require a complete current affordance set",
                "$.metadata.affordance_completeness",
            )
        if (
            self.metadata.source_kind is FixtureSourceKind.REAL_CAPTURE
            and not self.state.raw_capture_id
        ):
            raise _FixtureValidation(
                ErrorCode.FIXTURE_METADATA_INVALID,
                "REAL_CAPTURE fixtures require raw_capture_id",
                "$.state.raw_capture_id",
            )
        if (
            self.metadata.source_kind is FixtureSourceKind.REDUCED_REGRESSION
            and self.metadata.provenance is None
        ):
            raise _FixtureValidation(
                ErrorCode.FIXTURE_METADATA_INVALID,
                "REDUCED_REGRESSION fixtures require provenance",
                "$.metadata.provenance",
            )
        if (
            self.metadata.review_status is ReviewStatus.PROMOTED
            and not self.metadata.expectation_version
        ):
            raise _FixtureValidation(
                ErrorCode.FIXTURE_METADATA_INVALID,
                "PROMOTED fixtures require expectation_version",
                "$.metadata.expectation_version",
            )
        if (
            self.metadata.information_profile is InformationProfile.PLAYER_LEGAL
            and self.oracle_annotations is not None
        ):
            # Oracle data belongs to the envelope, never the TacticalState. Keeping it
            # here is legitimate and decision_input() below deliberately omits it.
            canonical_json_bytes(self.oracle_annotations)

    def replay_input(self) -> ReplayInput:
        normalized = self.normalized()
        # State annotations are non-identity fixture/authoring data. Canonical
        # action data, including omniscient-debug diagnostics, must remain intact
        # so the returned state still normalizes to its declared identity.
        decision_state = replace(
            normalized.state,
            annotations=None,
        ).normalized()
        return ReplayInput(
            fixture_id=normalized.metadata.fixture_id,
            state=decision_state,
            state_id=decision_state.state_id,
            information_profile=decision_state.information_profile,
            ruleset_content_fingerprint=decision_state.ruleset.content_fingerprint,
        )

    def to_dict(self) -> dict[str, JsonValue]:
        metadata = {
            "fixture_id": self.metadata.fixture_id,
            "source_kind": self.metadata.source_kind.value,
            "taxonomy": list(self.metadata.taxonomy),
            "severity": self.metadata.severity.value,
            "scenario_intent": self.metadata.scenario_intent,
            "ruleset_content_fingerprint": (self.metadata.ruleset_content_fingerprint),
            "information_profile": self.metadata.information_profile.value,
            "affordance_completeness": (self.metadata.affordance_completeness.value),
            "expectation_version": self.metadata.expectation_version,
            "review_status": self.metadata.review_status.value,
            "provenance": self.metadata.provenance,
        }
        return {
            "schema_version": self.schema_version,
            "metadata": metadata,
            "state": self.state.to_dict(),
            "state_hash": self.state_hash,
            "expectations": self.expectations,
            "oracle_annotations": self.oracle_annotations,
        }

    def to_json_bytes(self) -> bytes:
        return canonical_json_bytes(self.normalized().to_dict()) + b"\n"

    @classmethod
    def from_dict(cls, value: Mapping[str, JsonValue]) -> Self:
        _require_keys(
            value,
            {
                "schema_version",
                "metadata",
                "state",
                "state_hash",
                "expectations",
                "oracle_annotations",
            },
            "$",
        )
        metadata_value = _mapping(value["metadata"], "$.metadata")
        _require_keys(
            metadata_value,
            {
                "fixture_id",
                "source_kind",
                "taxonomy",
                "severity",
                "scenario_intent",
                "ruleset_content_fingerprint",
                "information_profile",
                "affordance_completeness",
                "expectation_version",
                "review_status",
                "provenance",
            },
            "$.metadata",
        )
        try:
            metadata = FixtureMetadata(
                fixture_id=_string(metadata_value["fixture_id"], "fixture_id"),
                source_kind=FixtureSourceKind(
                    _string(metadata_value["source_kind"], "source_kind")
                ),
                taxonomy=tuple(
                    _string(tag, "taxonomy tag")
                    for tag in _sequence(metadata_value["taxonomy"], "taxonomy")
                ),
                severity=FixtureSeverity(
                    _string(metadata_value["severity"], "severity")
                ),
                scenario_intent=_string(
                    metadata_value["scenario_intent"], "scenario_intent"
                ),
                ruleset_content_fingerprint=_string(
                    metadata_value["ruleset_content_fingerprint"],
                    "ruleset_content_fingerprint",
                ),
                information_profile=InformationProfile(
                    _string(
                        metadata_value["information_profile"], "information_profile"
                    )
                ),
                affordance_completeness=AffordanceCompleteness(
                    _string(
                        metadata_value["affordance_completeness"],
                        "affordance_completeness",
                    )
                ),
                expectation_version=(
                    None
                    if metadata_value["expectation_version"] is None
                    else _string(
                        metadata_value["expectation_version"], "expectation_version"
                    )
                ),
                review_status=ReviewStatus(
                    _string(metadata_value["review_status"], "review_status")
                ),
                provenance=metadata_value["provenance"],
            )
        except (TypeError, ValueError) as error:
            raise _FixtureValidation(
                ErrorCode.FIXTURE_METADATA_INVALID, str(error), "$.metadata"
            ) from error
        state_value = _mapping(value["state"], "$.state")
        try:
            state = TacticalState.from_dict(dict(state_value))
        except (TypeError, ValueError, KeyError) as error:
            message = str(error)
            if "state_id does not match" in message:
                code = ErrorCode.FIXTURE_STATE_HASH_MISMATCH
            elif "stale affordance" in message:
                code = ErrorCode.FIXTURE_AFFORDANCE_MISMATCH
            else:
                code = ErrorCode.FIXTURE_STATE_INVALID
            raise _FixtureValidation(code, str(error), "$.state") from error
        envelope = cls(
            schema_version=_string(value["schema_version"], "schema_version"),
            metadata=metadata,
            state=state,
            state_hash=_string(value["state_hash"], "state_hash"),
            expectations=value["expectations"],
            oracle_annotations=value["oracle_annotations"],
        )
        return envelope.normalized()


class _FixtureValidation(ValueError):
    def __init__(self, code: ErrorCode, message: str, path: str) -> None:
        super().__init__(message)
        self.code = code
        self.path = path


def load_fixture(source: str | bytes | bytearray | Path) -> Result[FixtureEnvelope]:
    """Load one fixture from JSON bytes/text/path with structured diagnostics."""
    try:
        payload = _read_source(source)
    except OSError as error:
        return _failure(ErrorCode.FIXTURE_IO_FAILED, str(error), "$")
    try:
        value = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return _failure(ErrorCode.FIXTURE_JSON_INVALID, str(error), "$")
    if not isinstance(value, dict):
        return _failure(
            ErrorCode.FIXTURE_JSON_INVALID, "fixture root must be an object", "$"
        )
    try:
        fixture = FixtureEnvelope.from_dict(value)
    except _FixtureValidation as error:
        return _failure(error.code, str(error), error.path)
    except (TypeError, ValueError, KeyError) as error:
        return _failure(ErrorCode.FIXTURE_METADATA_INVALID, str(error), "$")
    return Result.success(fixture)


def save_fixture(path: str | Path, fixture: FixtureEnvelope) -> Result[Path]:
    """Write canonical UTF-8 fixture JSON without runtime/UI dependencies."""
    try:
        normalized = fixture.normalized()
        destination = Path(path)
        destination.write_bytes(normalized.to_json_bytes())
    except _FixtureValidation as error:
        return _failure(error.code, str(error), error.path)
    except (OSError, TypeError, ValueError) as error:
        return _failure(ErrorCode.FIXTURE_IO_FAILED, str(error), "$")
    return Result.success(destination)


def validate_fixture_pair(
    legal: FixtureEnvelope, debug: FixtureEnvelope
) -> Result[tuple[FixtureEnvelope, FixtureEnvelope]]:
    """Validate a legal/debug pair derived from one raw game capture."""
    try:
        legal = legal.normalized()
        debug = debug.normalized()
    except _FixtureValidation as error:
        return _failure(error.code, str(error), error.path)
    reasons: list[str] = []
    if legal.state.information_profile is not InformationProfile.PLAYER_LEGAL:
        reasons.append("legal fixture is not player_legal")
    if debug.state.information_profile is not InformationProfile.OMNISCIENT_DEBUG:
        reasons.append("debug fixture is not omniscient_debug")
    if not legal.state.raw_capture_id:
        reasons.append("paired fixtures require a nonempty raw_capture_id")
    if legal.state.raw_capture_id != debug.state.raw_capture_id:
        reasons.append("paired fixtures do not share raw_capture_id")
    if legal.state.state_id == debug.state.state_id:
        reasons.append("paired profile views must have distinct state IDs")
    if legal.state.ruleset != debug.state.ruleset:
        reasons.append("paired fixtures do not share ruleset identity")
    incompatibility = _cross_view_incompatibility(legal.state, debug.state)
    if incompatibility is not None:
        reasons.append(incompatibility)
    if reasons:
        return _failure(ErrorCode.FIXTURE_PAIR_MISMATCH, "; ".join(reasons), "$.state")
    return Result.success((legal, debug))


def _cross_view_incompatibility(
    legal: TacticalState, debug: TacticalState
) -> str | None:
    """Return the first debug-view divergence that is not legitimate enrichment."""
    return _compare_cross_view(legal, debug, "$.state")


def _compare_cross_view(legal: Any, debug: Any, path: str) -> str | None:
    if type(legal) is not type(debug):
        return f"paired fixtures differ at {path}"
    if isinstance(legal, KnownValue):
        if debug.knowledge_class is KnowledgeClass.DEBUG_GROUND_TRUTH:
            if _debug_value_is_compatible(legal, debug):
                return None
            return f"debug truth contradicts legal-view knowledge at {path}"
    if is_dataclass(legal):
        ignored = _cross_view_ignored_fields(legal)
        for item in fields(legal):
            if item.name in ignored:
                continue
            legal_value = getattr(legal, item.name)
            debug_value = getattr(debug, item.name)
            key_name = _keyed_collection_key(legal, item.name)
            if key_name is not None:
                mismatch = _compare_keyed_collection(
                    legal_value,
                    debug_value,
                    key_name,
                    f"{path}.{item.name}",
                )
                if mismatch is not None:
                    return mismatch
                continue
            mismatch = _compare_cross_view(
                legal_value,
                debug_value,
                f"{path}.{item.name}",
            )
            if mismatch is not None:
                return mismatch
        return None
    if isinstance(legal, tuple):
        if len(legal) != len(debug):
            return f"paired fixtures differ at {path}"
        for index, (legal_child, debug_child) in enumerate(zip(legal, debug)):
            mismatch = _compare_cross_view(legal_child, debug_child, f"{path}[{index}]")
            if mismatch is not None:
                return mismatch
        return None
    if legal != debug:
        return f"paired fixtures differ at {path}"
    return None


def _debug_value_is_compatible(legal: KnownValue, debug: KnownValue) -> bool:
    if legal.representation is Representation.UNKNOWN:
        return True
    if debug.representation is Representation.RANGE:
        if legal.representation is Representation.RANGE:
            return _within_range(debug.minimum, legal.minimum, legal.maximum) and (
                _within_range(debug.maximum, legal.minimum, legal.maximum)
            )
        if debug.minimum != debug.maximum:
            return False
        debug_domain = (debug.minimum,)
    else:
        debug_domain = _discrete_domain(debug)
    if debug_domain is None:
        return False
    if legal.representation is Representation.RANGE:
        return all(
            _within_range(value, legal.minimum, legal.maximum) for value in debug_domain
        )
    legal_domain = _discrete_domain(legal)
    if legal_domain is None:
        return False
    return all(_json_member(value, legal_domain) for value in debug_domain)


def _discrete_domain(value: KnownValue) -> tuple[JsonValue, ...] | None:
    if value.representation is Representation.EXACT:
        return (value.value,)
    if value.representation is Representation.SET:
        return value.candidates
    if value.representation is Representation.DISTRIBUTION:
        return tuple(
            outcome for outcome, probability in value.distribution if probability > 0
        )
    if value.representation is Representation.RANGE and value.minimum == value.maximum:
        return (value.minimum,)
    return None


def _within_range(value: Any, minimum: Any, maximum: Any) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and minimum <= value <= maximum
    )


def _same_json(first: JsonValue, second: JsonValue) -> bool:
    return canonical_json_bytes(first) == canonical_json_bytes(second)


def _json_member(value: JsonValue, candidates: Sequence[JsonValue]) -> bool:
    return any(_same_json(value, candidate) for candidate in candidates)


def _compare_keyed_collection(
    legal: tuple[Any, ...],
    debug: tuple[Any, ...],
    key_name: str | int,
    path: str,
) -> str | None:
    def key(value: Any) -> str:
        return (
            value[key_name] if isinstance(key_name, int) else getattr(value, key_name)
        )

    legal_by_key = {key(value): value for value in legal}
    debug_by_key = {key(value): value for value in debug}
    missing = sorted(set(legal_by_key) - set(debug_by_key))
    if missing:
        return f"debug view omits legal-view items at {path}: {missing}"
    for item_key in sorted(legal_by_key):
        mismatch = _compare_cross_view(
            legal_by_key[item_key], debug_by_key[item_key], f"{path}[{item_key}]"
        )
        if mismatch is not None:
            return mismatch
    for item_key in sorted(set(debug_by_key) - set(legal_by_key)):
        if not _is_debug_only_item(debug_by_key[item_key], key_name):
            return f"unmarked debug-only item at {path}[{item_key}]"
    return None


def _keyed_collection_key(owner: Any, field_name: str) -> str | int | None:
    keys: dict[tuple[type[Any], str], str | int] = {
        (TacticalState, "combatants"): "actor_id",
        (TacticalState, "ground_entities"): "entity_id",
        (Combatant, "equipment"): "item_id",
        (Combatant, "effects"): "effect_id",
        (Combatant, "skills"): "skill_id",
        (Combatant, "tactical_stats"): "stat_id",
        (TurnState, "entries"): "actor_id",
        (GroundEntity, "state"): 0,
    }
    return keys.get((type(owner), field_name))


def _is_debug_only_item(value: Any, key_name: str | int) -> bool:
    if isinstance(value, Combatant):
        marker = (value.position, value.content_identity)
    elif isinstance(value, GroundEntity):
        marker = (value.content, value.position)
    elif isinstance(value, ItemState | EffectState):
        marker = (value.membership,)
    elif isinstance(value, SkillState):
        marker = (value.possession,)
    elif isinstance(value, TacticalStat):
        marker = (value.value,)
    elif isinstance(value, TurnEntry):
        marker = (value.done, value.sequence)
    elif isinstance(value, tuple) and key_name == 0:
        marker = (value[1],)
    else:
        return False
    return any(
        isinstance(item, KnownValue)
        and item.knowledge_class is KnowledgeClass.DEBUG_GROUND_TRUTH
        for item in marker
    )


def _cross_view_ignored_fields(value: Any) -> set[str]:
    if isinstance(value, TacticalState):
        return {"state_id", "raw_capture_id", "information_profile", "annotations"}
    if isinstance(value, ActionAffordance):
        return {"debug_ground_truth"}
    if isinstance(value, ActionAffordanceSet):
        return {"captured_for_state_id"}
    return set()


def _read_source(source: str | bytes | bytearray | Path) -> str | bytes:
    if isinstance(source, Path):
        return source.read_bytes()
    if isinstance(source, bytes | bytearray):
        return bytes(source)
    stripped = source.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return source
    return Path(source).read_bytes()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _failure[T](code: ErrorCode, message: str, path: str) -> Result[T]:
    return Result.validation_failure(Problem(code=code, message=message, path=path))


def _mapping(value: JsonValue, path: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise _FixtureValidation(
            ErrorCode.FIXTURE_METADATA_INVALID, "expected an object", path
        )
    return value


def _sequence(value: JsonValue, name: str) -> Sequence[JsonValue]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        raise ValueError(f"{name} must be an array")
    return value


def _string(value: JsonValue, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _require_keys(
    value: Mapping[str, JsonValue], expected: set[str], path: str
) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise _FixtureValidation(
            ErrorCode.FIXTURE_METADATA_INVALID,
            f"unexpected object keys (missing={missing}, extra={extra})",
            path,
        )
