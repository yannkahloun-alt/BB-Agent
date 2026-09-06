"""Development-only paired ingest for player-legal and omniscient oracle twins."""

from __future__ import annotations

from dataclasses import replace

from bb_agent.live_ingest import (
    AcceptedLiveDecision,
    LiveCompatibility,
    LiveIngestEvent,
    LiveIngestMachine,
    LiveIngestStatus,
    LiveRecord,
    LiveRecordType,
)


class PairedLiveIngestMachine:
    """Keep production advice and debug-oracle state physically independent.

    The production plane always has ``allow_debug=False``. The debug plane is
    enabled only when the caller explicitly supplies ``allow_debug=True``.
    Both planes receive the same STREAM_START and therefore share the same
    capture-stream identity, which makes raw-capture correlation deterministic.
    """

    def __init__(
        self,
        compatibility: LiveCompatibility,
        *,
        stream_id_factory=None,
    ) -> None:
        self.compatibility = compatibility
        self._stream_id_factory = stream_id_factory
        self._production = LiveIngestMachine(
            replace(compatibility, allow_debug=False),
            stream_id_factory=stream_id_factory,
        )
        self._debug = LiveIngestMachine(
            replace(compatibility, allow_debug=True),
            stream_id_factory=self._debug_stream_id,
        )
        self._authoritative_key = (-1, -1)

    def _debug_stream_id(self) -> str:
        stream_id = self._production.capture_stream_id
        if stream_id is None:
            raise ValueError("debug stream cannot start before production stream")
        return stream_id

    @property
    def capture_stream_id(self) -> str | None:
        return self._production.capture_stream_id

    @property
    def current_decision(self) -> AcceptedLiveDecision | None:
        """Return only the player-legal externally usable decision."""

        return self._production.current_decision

    @property
    def current_debug_decision(self) -> AcceptedLiveDecision | None:
        """Return the latest accepted oracle twin for validation tooling only."""

        return self._debug.current_decision

    def accept(self, record: LiveRecord) -> LiveIngestEvent:
        if record.record_type is LiveRecordType.STREAM_START:
            production_event = self._production.accept(record)
            if production_event.status is LiveIngestStatus.STREAM_STARTED:
                self._authoritative_key = (-1, -1)
                self._debug.accept(record)
            return production_event

        if (
            record.record_type is LiveRecordType.DECISION_READY
            and record.information_profile == "omniscient_debug"
        ):
            if not self.compatibility.allow_debug:
                return LiveIngestEvent(
                    LiveIngestStatus.REJECTED_INCOMPATIBLE,
                    "omniscient_debug live records are disabled",
                    record=record,
                )
            if self.capture_stream_id is None:
                return LiveIngestEvent(
                    LiveIngestStatus.REJECTED_STALE,
                    "debug record arrived before a valid STREAM_START",
                    record=record,
                )
            assert record.battle_sequence is not None
            assert record.source_generation is not None
            key = (record.battle_sequence, record.source_generation)
            if key < self._authoritative_key:
                return LiveIngestEvent(
                    LiveIngestStatus.REJECTED_STALE,
                    f"stale debug generation {key}; production is {self._authoritative_key}",
                    record=record,
                )
            return self._debug.accept(record)

        production_event = self._production.accept(record)
        if record.record_type is LiveRecordType.DECISION_INVALIDATED:
            if production_event.status is LiveIngestStatus.INVALIDATED:
                assert record.battle_sequence is not None
                assert record.source_generation is not None
                self._authoritative_key = (
                    record.battle_sequence,
                    record.source_generation,
                )
                self._debug.accept(record)
            return production_event

        if (
            record.record_type is LiveRecordType.DECISION_READY
            and record.information_profile == "player_legal"
            and production_event.status
            in {LiveIngestStatus.READY, LiveIngestStatus.DUPLICATE}
        ):
            assert record.battle_sequence is not None
            assert record.source_generation is not None
            self._authoritative_key = (
                record.battle_sequence,
                record.source_generation,
            )
        return production_event
