"""Fail-closed ingest for post-M1 Battle Brothers live-envelope records."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from bb_agent.evaluator import (
    DEFAULT_EVALUATION_PROFILE,
    DEFAULT_UNIT_VALUE_POLICY,
)
from bb_agent.evaluator import (
    MODEL_VERSION as EVALUATOR_MODEL_VERSION,
)
from bb_agent.mechanics import load_builtin_mechanics
from bb_agent.results import ResultStatus
from bb_agent.serialization import JsonValue, canonical_json_bytes, canonical_sha256
from bb_agent.trace import TRACE_VERSION
from bb_agent.versions import CURRENT_VERSIONS

LIVE_ENVELOPE_VERSION = "bb-agent-live-envelope.v1"
LIVE_CAPTURE_VERSION = "bb-agent-live-capture.v1"
LIVE_FRAME_PREFIX = "BBAGENT1"
DEFAULT_MAX_DECODED_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_ENCODED_BYTES = 3 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FRAME_RE = re.compile(rb"BBAGENT1\|([0-9]+)\|([0-9a-f]{64})\|([A-Za-z0-9_-]+)$")
_TEXT_DIV_OPEN = b'<div class="text">'
_TEXT_DIV_CLOSE = b"</div>"


@dataclass(frozen=True, slots=True)
class LiveKernelIdentity:
    """Kernel-side contracts a live producer claims its payload targets."""

    m1_spec: str
    information_policy: str
    tactical_state: str
    action_affordance: str
    evaluation_contract: str
    uncertainty_contract: str
    decision_trace_contract: str
    trace_schema: str
    evaluator_model: str
    evaluation_config: str
    mechanics_manifest: str
    mechanics_manifest_fingerprint: str
    evaluation_profile_fingerprint: str
    unit_value_policy_version: str
    unit_value_policy_fingerprint: str
    outcome_model: str

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not isinstance(value, str) or not value:
                raise ValueError(f"kernel identity {name} must be a nonempty string")
        for name in (
            "mechanics_manifest_fingerprint",
            "evaluation_profile_fingerprint",
            "unit_value_policy_fingerprint",
        ):
            if _SHA256_RE.fullmatch(getattr(self, name)) is None:
                raise ValueError(f"kernel identity {name} must be lowercase SHA-256")

    def to_wire_dict(self) -> dict[str, str]:
        return asdict(self)


def current_live_kernel_identity() -> LiveKernelIdentity:
    """Return the exact closed-M1 identities expected by the live adapter."""

    authority_result = load_builtin_mechanics()
    if (
        authority_result.status is not ResultStatus.SUCCESS
        or authority_result.value is None
    ):
        raise RuntimeError(
            f"built-in mechanics identity unavailable: {authority_result.problems}"
        )
    return LiveKernelIdentity(
        m1_spec=CURRENT_VERSIONS.m1_spec,
        information_policy=CURRENT_VERSIONS.information_policy,
        tactical_state=CURRENT_VERSIONS.tactical_state,
        action_affordance=CURRENT_VERSIONS.action_affordance,
        evaluation_contract=CURRENT_VERSIONS.evaluation,
        uncertainty_contract=CURRENT_VERSIONS.uncertainty,
        decision_trace_contract=CURRENT_VERSIONS.decision_trace,
        trace_schema=TRACE_VERSION,
        evaluator_model=EVALUATOR_MODEL_VERSION,
        evaluation_config=CURRENT_VERSIONS.evaluation_config,
        mechanics_manifest=CURRENT_VERSIONS.mechanics_manifest,
        mechanics_manifest_fingerprint=authority_result.value.manifest.fingerprint,
        evaluation_profile_fingerprint=DEFAULT_EVALUATION_PROFILE.fingerprint,
        unit_value_policy_version=DEFAULT_UNIT_VALUE_POLICY.version,
        unit_value_policy_fingerprint=DEFAULT_UNIT_VALUE_POLICY.fingerprint,
        outcome_model=CURRENT_VERSIONS.outcome_model,
    )


class LiveRecordType(StrEnum):
    STREAM_START = "STREAM_START"
    DECISION_READY = "DECISION_READY"
    DECISION_INVALIDATED = "DECISION_INVALIDATED"


class LiveIngestStatus(StrEnum):
    STREAM_STARTED = "STREAM_STARTED"
    READY = "READY"
    INVALIDATED = "INVALIDATED"
    DUPLICATE = "DUPLICATE"
    IGNORED_NON_PROTOCOL = "IGNORED_NON_PROTOCOL"
    REJECTED_MALFORMED = "REJECTED_MALFORMED"
    REJECTED_INCOMPATIBLE = "REJECTED_INCOMPATIBLE"
    REJECTED_STALE = "REJECTED_STALE"
    REJECTED_CONFLICT = "REJECTED_CONFLICT"
    STREAM_DISCONTINUITY = "STREAM_DISCONTINUITY"


@dataclass(frozen=True, slots=True)
class LiveCompatibility:
    """Expected live-envelope identities for one external receiver."""

    ruleset_game_version: str
    ruleset_content_fingerprint: str
    expected_mods: tuple[str, ...] | None = None
    expected_companion_version: str | None = None
    expected_runtime_game_version: str | None = None
    envelope_version: str = LIVE_ENVELOPE_VERSION
    capture_contract_version: str = LIVE_CAPTURE_VERSION
    expected_kernel_identity: LiveKernelIdentity = field(
        default_factory=current_live_kernel_identity
    )
    allow_debug: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.ruleset_game_version, str)
            or not self.ruleset_game_version
        ):
            raise ValueError("ruleset_game_version cannot be empty")
        if (
            not isinstance(self.ruleset_content_fingerprint, str)
            or _SHA256_RE.fullmatch(self.ruleset_content_fingerprint) is None
        ):
            raise ValueError("ruleset_content_fingerprint must be lowercase SHA-256")
        if self.expected_mods is not None:
            if (
                isinstance(self.expected_mods, str | bytes | bytearray)
                or not isinstance(self.expected_mods, Sequence)
            ):
                raise ValueError("expected_mods must be an array of strings")
            object.__setattr__(self, "expected_mods", tuple(self.expected_mods))
            if any(not isinstance(mod, str) or not mod for mod in self.expected_mods):
                raise ValueError("expected_mods entries must be nonempty strings")
        if self.expected_companion_version is not None and (
            not isinstance(self.expected_companion_version, str)
            or not self.expected_companion_version
        ):
            raise ValueError("expected_companion_version cannot be empty")
        if self.expected_runtime_game_version is not None and (
            not isinstance(self.expected_runtime_game_version, str)
            or not self.expected_runtime_game_version
        ):
            raise ValueError("expected_runtime_game_version cannot be empty")
        if self.expected_mods is not None and self.expected_mods != tuple(
            sorted(self.expected_mods)
        ):
            raise ValueError("expected_mods must be sorted for stable identity")
        if self.envelope_version != LIVE_ENVELOPE_VERSION:
            raise ValueError("unsupported live envelope version")
        if self.capture_contract_version != LIVE_CAPTURE_VERSION:
            raise ValueError("unsupported live capture contract version")
        if not isinstance(self.expected_kernel_identity, LiveKernelIdentity):
            raise ValueError("expected_kernel_identity must be LiveKernelIdentity")
        if not isinstance(self.allow_debug, bool):
            raise ValueError("allow_debug must be a boolean")


@dataclass(frozen=True, slots=True)
class LiveRecord:
    """One validated producer-side live record before stream provenance is added."""

    record_type: LiveRecordType
    companion_version: str
    runtime_game_version: str
    ruleset_game_version: str
    ruleset_content_fingerprint: str
    mods: tuple[str, ...]
    kernel_identity: LiveKernelIdentity = field(
        default_factory=current_live_kernel_identity
    )
    battle_sequence: int | None = None
    source_generation: int | None = None
    raw_source_fingerprint: str | None = None
    information_profile: str | None = None
    payload: JsonValue = None
    reason: str | None = None

    def to_wire_dict(self) -> dict[str, JsonValue]:
        base: dict[str, JsonValue] = {
            "envelope_version": LIVE_ENVELOPE_VERSION,
            "capture_contract_version": LIVE_CAPTURE_VERSION,
            "record_type": self.record_type.value,
            "companion_version": self.companion_version,
            "runtime_game_version": self.runtime_game_version,
            "ruleset_game_version": self.ruleset_game_version,
            "ruleset_content_fingerprint": self.ruleset_content_fingerprint,
            "mods": list(self.mods),
            "kernel_identity": self.kernel_identity.to_wire_dict(),
        }
        if self.record_type is LiveRecordType.DECISION_READY:
            base.update(
                battle_sequence=self.battle_sequence,
                source_generation=self.source_generation,
                raw_source_fingerprint=self.raw_source_fingerprint,
                information_profile=self.information_profile,
                payload=_thaw_json(self.payload),
            )
        elif self.record_type is LiveRecordType.DECISION_INVALIDATED:
            base.update(
                battle_sequence=self.battle_sequence,
                source_generation=self.source_generation,
                reason=self.reason,
            )
        return base


@dataclass(frozen=True, slots=True)
class AcceptedLiveDecision:
    """A READY record after host stream provenance and semantic IDs are attached."""

    capture_stream_id: str
    raw_capture_id: str
    payload_digest: str
    record: LiveRecord


@dataclass(frozen=True, slots=True)
class LiveIngestEvent:
    status: LiveIngestStatus
    message: str
    decision: AcceptedLiveDecision | None = None
    record: LiveRecord | None = None
    frame_observed_ns: int | None = None
    canonical_available_ns: int | None = None

    @property
    def processing_latency_ns(self) -> int | None:
        if self.frame_observed_ns is None or self.canonical_available_ns is None:
            return None
        return self.canonical_available_ns - self.frame_observed_ns


@dataclass(slots=True)
class _MachineState:
    capture_stream_id: str | None = None
    battle_sequence: int = -1
    source_generation: int = -1
    current_raw_capture_id: str | None = None
    current_payload_digest: str | None = None
    last_record_type: LiveRecordType | None = None
    current_decision: AcceptedLiveDecision | None = None

    def clear_stream(self) -> None:
        self.capture_stream_id = None
        self.battle_sequence = -1
        self.source_generation = -1
        self.current_raw_capture_id = None
        self.current_payload_digest = None
        self.last_record_type = None
        self.current_decision = None


class LiveIngestMachine:
    """Apply compatibility, ordering, duplicate, and invalidation policy."""

    def __init__(
        self,
        compatibility: LiveCompatibility,
        *,
        stream_id_factory: Callable[[], str] | None = None,
        state: _MachineState | None = None,
    ) -> None:
        self.compatibility = compatibility
        self._stream_id_factory = stream_id_factory or (lambda: str(uuid.uuid4()))
        self._state = state or _MachineState()

    @property
    def current_decision(self) -> AcceptedLiveDecision | None:
        return self._state.current_decision

    @property
    def capture_stream_id(self) -> str | None:
        return self._state.capture_stream_id

    def invalidate_for_discontinuity(self) -> None:
        self._state.clear_stream()

    def invalidate_current_readiness(self) -> None:
        """Clear advice without discarding accepted stream/generation identity."""

        self._state.current_decision = None

    def accept(self, record: LiveRecord) -> LiveIngestEvent:
        incompatible = _compatibility_problem(record, self.compatibility)
        if incompatible is not None:
            if record.record_type is LiveRecordType.STREAM_START:
                self._state.clear_stream()
            else:
                self.invalidate_current_readiness()
            return LiveIngestEvent(
                LiveIngestStatus.REJECTED_INCOMPATIBLE, incompatible, record=record
            )

        if record.record_type is LiveRecordType.STREAM_START:
            stream_id = self._stream_id_factory()
            if not isinstance(stream_id, str) or not stream_id:
                raise ValueError("stream_id_factory must return a nonempty string")
            self._state.clear_stream()
            self._state.capture_stream_id = stream_id
            return LiveIngestEvent(
                LiveIngestStatus.STREAM_STARTED,
                f"capture stream started: {stream_id}",
                record=record,
            )

        if self._state.capture_stream_id is None:
            return LiveIngestEvent(
                LiveIngestStatus.REJECTED_STALE,
                "decision record arrived before a valid STREAM_START",
                record=record,
            )

        assert record.battle_sequence is not None
        assert record.source_generation is not None
        key = (record.battle_sequence, record.source_generation)
        prior = (self._state.battle_sequence, self._state.source_generation)
        if key < prior:
            return LiveIngestEvent(
                LiveIngestStatus.REJECTED_STALE,
                f"stale decision generation {key}; current is {prior}",
                record=record,
            )

        if record.record_type is LiveRecordType.DECISION_INVALIDATED:
            if key > prior:
                # There is no READY identity for this newer generation yet.
                self._state.current_raw_capture_id = None
                self._state.current_payload_digest = None
            self._state.battle_sequence, self._state.source_generation = key
            self._state.last_record_type = LiveRecordType.DECISION_INVALIDATED
            self._state.current_decision = None
            return LiveIngestEvent(
                LiveIngestStatus.INVALIDATED,
                f"decision invalidated: {record.reason}",
                record=record,
            )

        assert record.record_type is LiveRecordType.DECISION_READY
        assert record.raw_source_fingerprint is not None
        payload_digest = canonical_sha256(_thaw_json(record.payload))
        raw_capture_id = canonical_sha256(
            {
                "capture_stream_id": self._state.capture_stream_id,
                "battle_sequence": record.battle_sequence,
                "source_generation": record.source_generation,
                "raw_source_fingerprint": record.raw_source_fingerprint,
            }
        )

        if key == prior and self._state.current_raw_capture_id is None:
            self._state.current_decision = None
            return LiveIngestEvent(
                LiveIngestStatus.REJECTED_STALE,
                "generation was invalidated before a READY identity was established; "
                "a newer generation is required",
                record=record,
            )

        if key == prior and self._state.current_raw_capture_id is not None:
            if raw_capture_id != self._state.current_raw_capture_id:
                self._state.current_raw_capture_id = None
                self._state.current_payload_digest = None
                self._state.current_decision = None
                return LiveIngestEvent(
                    LiveIngestStatus.REJECTED_CONFLICT,
                    "same generation produced a different raw_capture_id",
                    record=record,
                )
            if payload_digest != self._state.current_payload_digest:
                self._state.current_raw_capture_id = None
                self._state.current_payload_digest = None
                self._state.current_decision = None
                return LiveIngestEvent(
                    LiveIngestStatus.REJECTED_CONFLICT,
                    "same raw_capture_id produced a different payload digest",
                    record=record,
                )
            if self._state.current_decision is None:
                self._state.current_decision = AcceptedLiveDecision(
                    self._state.capture_stream_id,
                    raw_capture_id,
                    payload_digest,
                    record,
                )
            self._state.last_record_type = LiveRecordType.DECISION_READY
            return LiveIngestEvent(
                LiveIngestStatus.DUPLICATE,
                "exact duplicate READY record",
                decision=self._state.current_decision,
                record=record,
            )

        decision = AcceptedLiveDecision(
            self._state.capture_stream_id,
            raw_capture_id,
            payload_digest,
            record,
        )
        self._state.battle_sequence, self._state.source_generation = key
        self._state.current_raw_capture_id = raw_capture_id
        self._state.current_payload_digest = payload_digest
        self._state.last_record_type = LiveRecordType.DECISION_READY
        self._state.current_decision = decision
        return LiveIngestEvent(
            LiveIngestStatus.READY,
            "decision READY accepted",
            decision=decision,
            record=record,
        )

    def to_persisted_dict(self) -> dict[str, JsonValue]:
        return {
            "capture_stream_id": self._state.capture_stream_id,
            "battle_sequence": self._state.battle_sequence,
            "source_generation": self._state.source_generation,
            "current_raw_capture_id": self._state.current_raw_capture_id,
            "current_payload_digest": self._state.current_payload_digest,
            "last_record_type": (
                self._state.last_record_type.value
                if self._state.last_record_type is not None
                else None
            ),
            "current_ready_record": (
                self._state.current_decision.record.to_wire_dict()
                if self._state.current_decision is not None
                else None
            ),
        }

    @classmethod
    def from_persisted_dict(
        cls,
        compatibility: LiveCompatibility,
        value: Mapping[str, JsonValue],
        *,
        stream_id_factory: Callable[[], str] | None = None,
    ) -> LiveIngestMachine:
        required = {
            "capture_stream_id",
            "battle_sequence",
            "source_generation",
            "current_raw_capture_id",
            "current_payload_digest",
            "last_record_type",
            "current_ready_record",
        }
        if set(value) != required:
            raise ValueError("persisted live-ingest state fields do not match schema")
        capture_stream_id = _optional_string(
            value["capture_stream_id"], "capture_stream_id"
        )
        battle_sequence = _integer(
            value["battle_sequence"], "battle_sequence", minimum=-1
        )
        source_generation = _integer(
            value["source_generation"], "source_generation", minimum=-1
        )
        raw_capture_id = _optional_sha(
            value["current_raw_capture_id"], "raw_capture_id"
        )
        payload_digest = _optional_sha(
            value["current_payload_digest"], "payload_digest"
        )
        last_record_type_value = value["last_record_type"]
        if last_record_type_value is None:
            last_record_type = None
        else:
            try:
                last_record_type = LiveRecordType(
                    _string(last_record_type_value, "last_record_type")
                )
            except ValueError as exc:
                raise ValueError("persisted last_record_type is invalid") from exc
            if last_record_type is LiveRecordType.STREAM_START:
                raise ValueError("persisted last_record_type cannot be STREAM_START")
        if capture_stream_id is None:
            if (
                any(item is not None for item in (raw_capture_id, payload_digest))
                or last_record_type is not None
                or (battle_sequence, source_generation) != (-1, -1)
            ):
                raise ValueError(
                    "empty stream cannot carry persisted decision identity"
                )
        if (raw_capture_id is None) != (payload_digest is None):
            raise ValueError("persisted current decision identity is incomplete")
        current_ready_value = value["current_ready_record"]
        current_decision = None
        if current_ready_value is not None:
            if not isinstance(current_ready_value, Mapping):
                raise ValueError("persisted current_ready_record must be an object")
            current_record = _record_from_wire_dict(current_ready_value)
            if current_record.record_type is not LiveRecordType.DECISION_READY:
                raise ValueError("persisted current_ready_record must be READY")
            problem = _compatibility_problem(current_record, compatibility)
            if problem is not None:
                raise ValueError(f"persisted current READY is incompatible: {problem}")
            if (
                capture_stream_id is None
                or raw_capture_id is None
                or payload_digest is None
            ):
                raise ValueError("persisted current READY identity is incomplete")
            if (current_record.battle_sequence, current_record.source_generation) != (
                battle_sequence,
                source_generation,
            ):
                raise ValueError("persisted current READY generation mismatch")
            expected_digest = canonical_sha256(_thaw_json(current_record.payload))
            expected_raw_capture_id = canonical_sha256(
                {
                    "capture_stream_id": capture_stream_id,
                    "battle_sequence": current_record.battle_sequence,
                    "source_generation": current_record.source_generation,
                    "raw_source_fingerprint": current_record.raw_source_fingerprint,
                }
            )
            if (
                expected_digest != payload_digest
                or expected_raw_capture_id != raw_capture_id
            ):
                raise ValueError("persisted current READY digest/identity mismatch")
            current_decision = AcceptedLiveDecision(
                capture_stream_id, raw_capture_id, payload_digest, current_record
            )
        if (
            last_record_type is not LiveRecordType.DECISION_READY
            and current_decision is not None
        ):
            raise ValueError("persisted current READY contradicts last record type")
        state = _MachineState(
            capture_stream_id=capture_stream_id,
            battle_sequence=battle_sequence,
            source_generation=source_generation,
            current_raw_capture_id=raw_capture_id,
            current_payload_digest=payload_digest,
            last_record_type=last_record_type,
            current_decision=current_decision,
        )
        return cls(compatibility, stream_id_factory=stream_id_factory, state=state)


def encode_live_frame(record: LiveRecord) -> str:
    """Encode one producer record with deterministic length/integrity framing."""

    _validate_record(record)
    raw = canonical_json_bytes(record.to_wire_dict())
    digest = hashlib.sha256(raw).hexdigest()
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{LIVE_FRAME_PREFIX}|{len(raw)}|{digest}|{encoded}"


def decode_live_frame(
    frame: str | bytes,
    *,
    max_decoded_bytes: int = DEFAULT_MAX_DECODED_BYTES,
    max_encoded_bytes: int = DEFAULT_MAX_ENCODED_BYTES,
) -> LiveRecord:
    """Validate one BBAGENT1 frame and decode its strict record schema."""

    if max_decoded_bytes <= 0 or max_encoded_bytes <= 0:
        raise ValueError("live frame size bounds must be positive")
    raw_frame = frame.encode("ascii") if isinstance(frame, str) else bytes(frame)
    if len(raw_frame) > max_encoded_bytes:
        raise ValueError("live frame exceeds encoded size limit")
    match = _FRAME_RE.fullmatch(raw_frame)
    if match is None:
        raise ValueError("malformed live frame")
    expected_length = int(match.group(1))
    if expected_length > max_decoded_bytes:
        raise ValueError("live payload exceeds decoded size limit")
    digest = match.group(2).decode("ascii")
    encoded = match.group(3)
    padding = b"=" * ((4 - len(encoded) % 4) % 4)
    try:
        payload = base64.urlsafe_b64decode(encoded + padding)
    except Exception as exc:
        raise ValueError("live payload base64 decode failed") from exc
    if len(payload) != expected_length:
        raise ValueError("live payload length mismatch")
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("live payload SHA-256 mismatch")
    try:
        decoded = json.loads(
            payload,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("live payload JSON decode failed") from exc
    if not isinstance(decoded, dict):
        raise ValueError("live payload root must be an object")
    if canonical_json_bytes(decoded) != payload:
        raise ValueError("live payload is not canonical JSON")
    return _record_from_wire_dict(decoded)


@dataclass(slots=True)
class _CursorState:
    file_identity: str
    offset: int
    anchor_start: int
    anchor_sha256: str


class LiveLogTailer:
    """Tail complete log HTML records with durable, fail-closed restart state."""

    STATE_VERSION = "bb-agent-live-ingest-state.v1"
    ANCHOR_BYTES = 256

    def __init__(
        self,
        log_path: str | Path,
        state_path: str | Path,
        compatibility: LiveCompatibility,
        *,
        stream_id_factory: Callable[[], str] | None = None,
        max_decoded_bytes: int = DEFAULT_MAX_DECODED_BYTES,
        max_encoded_bytes: int = DEFAULT_MAX_ENCODED_BYTES,
    ) -> None:
        self.log_path = Path(log_path)
        self.state_path = Path(state_path)
        self.compatibility = compatibility
        self.max_decoded_bytes = max_decoded_bytes
        self.max_encoded_bytes = max_encoded_bytes
        self._stream_id_factory = stream_id_factory
        self._cursor: _CursorState | None = None
        self._machine = LiveIngestMachine(
            compatibility, stream_id_factory=stream_id_factory
        )
        self._had_persisted_state = self.state_path.exists()
        if self._had_persisted_state:
            self._load_persisted_state()

    @property
    def current_decision(self) -> AcceptedLiveDecision | None:
        return self._machine.current_decision

    def poll(self) -> tuple[LiveIngestEvent, ...]:
        if not self.log_path.exists():
            if self._cursor is not None:
                self._invalidate_discontinuity("log file disappeared")
                self._persist_state()
                return (
                    LiveIngestEvent(
                        LiveIngestStatus.STREAM_DISCONTINUITY,
                        "log file disappeared; waiting for fresh STREAM_START",
                    ),
                )
            return ()

        stat = self.log_path.stat()
        identity = _file_identity(stat)
        if self._cursor is None:
            self._cursor = _CursorState(identity, 0, 0, _sha256_bytes(b""))
        elif (
            identity != self._cursor.file_identity or stat.st_size < self._cursor.offset
        ):
            reason = (
                "log file identity changed"
                if identity != self._cursor.file_identity
                else "log file truncated before persisted cursor"
            )
            self._invalidate_discontinuity(reason)
            # Recovery after a known prior cursor is deliberately conservative:
            # start at current EOF and wait for a future STREAM_START.
            self._cursor = self._cursor_at_eof(identity, stat.st_size)
            self._persist_state()
            return (
                LiveIngestEvent(
                    LiveIngestStatus.STREAM_DISCONTINUITY,
                    f"{reason}; waiting for fresh STREAM_START",
                ),
            )

        if not self._cursor_anchor_matches():
            reason = (
                "persisted cursor anchor no longer matches log"
                if self._had_persisted_state
                else "live cursor anchor no longer matches log"
            )
            self._invalidate_discontinuity(reason)
            self._cursor = self._cursor_at_eof(identity, stat.st_size)
            self._had_persisted_state = False
            self._persist_state()
            return (
                LiveIngestEvent(
                    LiveIngestStatus.STREAM_DISCONTINUITY,
                    f"{reason}; waiting for fresh STREAM_START",
                ),
            )
        self._had_persisted_state = False

        events, consumed_offset = self._read_complete_divs(self._cursor.offset)
        if consumed_offset != self._cursor.offset:
            self._cursor = self._cursor_for_offset(identity, consumed_offset)
            self._persist_state()
        return tuple(events)

    def _read_complete_divs(self, offset: int) -> tuple[list[LiveIngestEvent], int]:
        with self.log_path.open("rb") as handle:
            handle.seek(offset)
            chunk = handle.read()
        events: list[LiveIngestEvent] = []
        scan = 0
        consumed = 0
        while True:
            close = chunk.find(_TEXT_DIV_CLOSE, scan)
            if close < 0:
                break
            end = close + len(_TEXT_DIV_CLOSE)
            segment = chunk[scan:end]
            open_at = segment.rfind(_TEXT_DIV_OPEN)
            if open_at >= 0:
                content = segment[open_at + len(_TEXT_DIV_OPEN) : -len(_TEXT_DIV_CLOSE)]
                if content.startswith((LIVE_FRAME_PREFIX + "|").encode("ascii")):
                    observed_ns = time.monotonic_ns()
                    try:
                        record = decode_live_frame(
                            content,
                            max_decoded_bytes=self.max_decoded_bytes,
                            max_encoded_bytes=self.max_encoded_bytes,
                        )
                        event = self._machine.accept(record)
                    except ValueError as exc:
                        self._machine.invalidate_current_readiness()
                        event = LiveIngestEvent(
                            LiveIngestStatus.REJECTED_MALFORMED, str(exc)
                        )
                    event = replace(
                        event,
                        frame_observed_ns=observed_ns,
                        canonical_available_ns=time.monotonic_ns(),
                    )
                    if event.status is LiveIngestStatus.STREAM_STARTED:
                        # On first-ever attach, historical streams before the latest
                        # STREAM_START are not useful output. Clearing here means one
                        # poll returns only the latest stream's semantic events.
                        events.clear()
                    events.append(event)
            consumed = end
            scan = end
        return events, offset + consumed

    def _cursor_anchor_matches(self) -> bool:
        assert self._cursor is not None
        with self.log_path.open("rb") as handle:
            handle.seek(self._cursor.anchor_start)
            current = handle.read(self._cursor.offset - self._cursor.anchor_start)
        return _sha256_bytes(current) == self._cursor.anchor_sha256

    def _cursor_for_offset(self, identity: str, offset: int) -> _CursorState:
        start = max(0, offset - self.ANCHOR_BYTES)
        with self.log_path.open("rb") as handle:
            handle.seek(start)
            anchor = handle.read(offset - start)
        return _CursorState(identity, offset, start, _sha256_bytes(anchor))

    def _cursor_at_eof(self, identity: str, size: int) -> _CursorState:
        return self._cursor_for_offset(identity, size)

    def _invalidate_discontinuity(self, _reason: str) -> None:
        self._machine.invalidate_for_discontinuity()

    def _load_persisted_state(self) -> None:
        try:
            decoded = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("live ingest persisted state is unreadable") from exc
        if not isinstance(decoded, dict) or set(decoded) != {
            "state_version",
            "cursor",
            "machine",
        }:
            raise ValueError("live ingest persisted state fields do not match schema")
        if decoded["state_version"] != self.STATE_VERSION:
            raise ValueError("live ingest persisted state version mismatch")
        cursor = decoded["cursor"]
        machine = decoded["machine"]
        if not isinstance(cursor, dict) or not isinstance(machine, dict):
            raise ValueError("live ingest persisted state sections must be objects")
        if set(cursor) != {
            "file_identity",
            "offset",
            "anchor_start",
            "anchor_sha256",
        }:
            raise ValueError("live ingest cursor fields do not match schema")
        self._cursor = _CursorState(
            _string(cursor["file_identity"], "file_identity"),
            _integer(cursor["offset"], "offset", minimum=0),
            _integer(cursor["anchor_start"], "anchor_start", minimum=0),
            _sha(cursor["anchor_sha256"], "anchor_sha256"),
        )
        if self._cursor.anchor_start > self._cursor.offset:
            raise ValueError("live ingest anchor_start exceeds offset")
        if self._cursor.offset - self._cursor.anchor_start > self.ANCHOR_BYTES:
            raise ValueError("live ingest cursor anchor exceeds maximum span")
        self._machine = LiveIngestMachine.from_persisted_dict(
            self.compatibility,
            machine,
            stream_id_factory=self._stream_id_factory,
        )

    def _persist_state(self) -> None:
        if self._cursor is None:
            return
        value = {
            "state_version": self.STATE_VERSION,
            "cursor": asdict(self._cursor),
            "machine": self._machine.to_persisted_dict(),
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            dir=self.state_path.parent, prefix=self.state_path.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    value,
                    handle,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.state_path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _record_from_wire_dict(value: Mapping[str, JsonValue]) -> LiveRecord:
    common = {
        "envelope_version",
        "capture_contract_version",
        "record_type",
        "companion_version",
        "runtime_game_version",
        "ruleset_game_version",
        "ruleset_content_fingerprint",
        "mods",
        "kernel_identity",
    }
    if value.get("envelope_version") != LIVE_ENVELOPE_VERSION:
        raise ValueError("live envelope version mismatch")
    if value.get("capture_contract_version") != LIVE_CAPTURE_VERSION:
        raise ValueError("live capture contract version mismatch")
    try:
        record_type = LiveRecordType(_string(value.get("record_type"), "record_type"))
    except ValueError as exc:
        raise ValueError("unknown live record type") from exc
    required = set(common)
    if record_type is LiveRecordType.DECISION_READY:
        required |= {
            "battle_sequence",
            "source_generation",
            "raw_source_fingerprint",
            "information_profile",
            "payload",
        }
    elif record_type is LiveRecordType.DECISION_INVALIDATED:
        required |= {"battle_sequence", "source_generation", "reason"}
    if set(value) != required:
        raise ValueError("live record fields do not match strict schema")

    mods_value = value["mods"]
    if not isinstance(mods_value, Sequence) or isinstance(
        mods_value, str | bytes | bytearray
    ):
        raise ValueError("live mods must be an array of strings")
    mods = tuple(_string(item, "mod") for item in mods_value)
    if len(mods) != len(set(mods)):
        raise ValueError("live mods contain duplicates")

    kernel_identity_value = value["kernel_identity"]
    if not isinstance(kernel_identity_value, Mapping):
        raise ValueError("live kernel_identity must be an object")
    kernel_identity = _kernel_identity_from_wire(kernel_identity_value)

    common_args = dict(
        record_type=record_type,
        companion_version=_string(value["companion_version"], "companion_version"),
        runtime_game_version=_string(
            value["runtime_game_version"], "runtime_game_version"
        ),
        ruleset_game_version=_string(
            value["ruleset_game_version"], "ruleset_game_version"
        ),
        ruleset_content_fingerprint=_sha(
            value["ruleset_content_fingerprint"], "ruleset_content_fingerprint"
        ),
        mods=mods,
        kernel_identity=kernel_identity,
    )
    if record_type is LiveRecordType.STREAM_START:
        record = LiveRecord(**common_args)
    elif record_type is LiveRecordType.DECISION_INVALIDATED:
        record = LiveRecord(
            **common_args,
            battle_sequence=_integer(
                value["battle_sequence"], "battle_sequence", minimum=0
            ),
            source_generation=_integer(
                value["source_generation"], "source_generation", minimum=0
            ),
            reason=_string(value["reason"], "reason"),
        )
    else:
        profile = _string(value["information_profile"], "information_profile")
        if profile not in {"player_legal", "omniscient_debug"}:
            raise ValueError("unknown live information_profile")
        payload = value["payload"]
        if not isinstance(payload, Mapping):
            raise ValueError("DECISION_READY payload must be an object")
        record = LiveRecord(
            **common_args,
            battle_sequence=_integer(
                value["battle_sequence"], "battle_sequence", minimum=0
            ),
            source_generation=_integer(
                value["source_generation"], "source_generation", minimum=0
            ),
            raw_source_fingerprint=_sha(
                value["raw_source_fingerprint"], "raw_source_fingerprint"
            ),
            information_profile=profile,
            payload=_freeze_json(payload),
        )
    _validate_record(record)
    return record


def _kernel_identity_from_wire(value: Mapping[str, JsonValue]) -> LiveKernelIdentity:
    required = {
        "m1_spec",
        "information_policy",
        "tactical_state",
        "action_affordance",
        "evaluation_contract",
        "uncertainty_contract",
        "decision_trace_contract",
        "trace_schema",
        "evaluator_model",
        "evaluation_config",
        "mechanics_manifest",
        "mechanics_manifest_fingerprint",
        "evaluation_profile_fingerprint",
        "unit_value_policy_version",
        "unit_value_policy_fingerprint",
        "outcome_model",
    }
    if set(value) != required:
        raise ValueError("live kernel_identity fields do not match strict schema")
    return LiveKernelIdentity(
        **{name: _string(value[name], f"kernel_identity.{name}") for name in required}
    )


def _validate_record(record: LiveRecord) -> None:
    if not isinstance(record.record_type, LiveRecordType):
        raise ValueError("live record_type is invalid")
    for name, value in (
        ("companion_version", record.companion_version),
        ("runtime_game_version", record.runtime_game_version),
        ("ruleset_game_version", record.ruleset_game_version),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError(f"live {name} cannot be empty")
    _sha(record.ruleset_content_fingerprint, "ruleset_content_fingerprint")
    if not isinstance(record.mods, tuple):
        raise ValueError("live mods must be a tuple of strings")
    if any(not isinstance(mod, str) or not mod for mod in record.mods):
        raise ValueError("live mod identifiers must be nonempty strings")
    if len(record.mods) != len(set(record.mods)):
        raise ValueError("live mods contain duplicates")
    if record.mods != tuple(sorted(record.mods)):
        raise ValueError("live mods must be sorted for stable identity")
    if not isinstance(record.kernel_identity, LiveKernelIdentity):
        raise ValueError("live record kernel_identity is invalid")

    if record.record_type is LiveRecordType.STREAM_START:
        if (
            any(
                value is not None
                for value in (
                    record.battle_sequence,
                    record.source_generation,
                    record.raw_source_fingerprint,
                    record.information_profile,
                    record.reason,
                )
            )
            or record.payload is not None
        ):
            raise ValueError("STREAM_START carries decision-only fields")
        return

    if record.battle_sequence is None or record.source_generation is None:
        raise ValueError("decision records require battle/source generation")
    _integer(record.battle_sequence, "battle_sequence", minimum=0)
    _integer(record.source_generation, "source_generation", minimum=0)
    if record.record_type is LiveRecordType.DECISION_INVALIDATED:
        if not record.reason:
            raise ValueError("DECISION_INVALIDATED requires reason")
        if (
            any(
                value is not None
                for value in (
                    record.raw_source_fingerprint,
                    record.information_profile,
                )
            )
            or record.payload is not None
        ):
            raise ValueError("DECISION_INVALIDATED carries READY-only fields")
        return

    assert record.record_type is LiveRecordType.DECISION_READY
    if record.raw_source_fingerprint is None:
        raise ValueError("DECISION_READY requires raw_source_fingerprint")
    _sha(record.raw_source_fingerprint, "raw_source_fingerprint")
    if record.information_profile not in {"player_legal", "omniscient_debug"}:
        raise ValueError("DECISION_READY requires a known information_profile")
    if not isinstance(record.payload, Mapping):
        raise ValueError("DECISION_READY payload must be an object")
    if record.reason is not None:
        raise ValueError("DECISION_READY cannot carry invalidation reason")
    canonical_json_bytes(_thaw_json(record.payload))


def _compatibility_problem(
    record: LiveRecord, compatibility: LiveCompatibility
) -> str | None:
    if record.ruleset_game_version != compatibility.ruleset_game_version:
        return "ruleset game version mismatch"
    if record.ruleset_content_fingerprint != compatibility.ruleset_content_fingerprint:
        return "ruleset content fingerprint mismatch"
    if (
        compatibility.expected_companion_version is not None
        and record.companion_version != compatibility.expected_companion_version
    ):
        return "companion version mismatch"
    if (
        compatibility.expected_runtime_game_version is not None
        and record.runtime_game_version != compatibility.expected_runtime_game_version
    ):
        return "runtime game version mismatch"
    if (
        compatibility.expected_mods is not None
        and record.mods != compatibility.expected_mods
    ):
        return "mod stack mismatch"
    if record.kernel_identity != compatibility.expected_kernel_identity:
        return "kernel compatibility identity mismatch"
    if (
        record.information_profile == "omniscient_debug"
        and not compatibility.allow_debug
    ):
        return "omniscient_debug live records are disabled"
    return None


def _freeze_json(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze_json(child) for key, child in value.items()}
        )
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return tuple(_freeze_json(child) for child in value)
    return value


def _thaw_json(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return {key: _thaw_json(child) for key, child in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_thaw_json(child) for child in value]
    return value


def _unique_json_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate live JSON field: {key}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> JsonValue:
    raise ValueError(f"non-finite live JSON constant is forbidden: {value}")


def _string(value: JsonValue, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _optional_string(value: JsonValue, name: str) -> str | None:
    if value is None:
        return None
    return _string(value, name)


def _integer(value: JsonValue, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _sha(value: JsonValue, name: str) -> str:
    text = _string(value, name)
    if _SHA256_RE.fullmatch(text) is None:
        raise ValueError(f"{name} must be lowercase SHA-256")
    return text


def _optional_sha(value: JsonValue, name: str) -> str | None:
    if value is None:
        return None
    return _sha(value, name)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_identity(stat: os.stat_result) -> str:
    return f"{stat.st_dev}:{stat.st_ino}"
