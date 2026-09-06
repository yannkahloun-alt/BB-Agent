"""Opt-in pairing helpers for player-legal / omniscient-debug live twins."""

from __future__ import annotations

from dataclasses import dataclass

from bb_agent.live_ingest import LiveRecord, LiveRecordType
from bb_agent.serialization import canonical_sha256


@dataclass(frozen=True, slots=True)
class LiveDebugTwin:
    """Two semantic views of one raw Battle Brothers decision capture."""

    player_legal: LiveRecord
    omniscient_debug: LiveRecord

    @property
    def battle_sequence(self) -> int:
        assert self.player_legal.battle_sequence is not None
        return self.player_legal.battle_sequence

    @property
    def source_generation(self) -> int:
        assert self.player_legal.source_generation is not None
        return self.player_legal.source_generation

    @property
    def raw_source_fingerprint(self) -> str:
        assert self.player_legal.raw_source_fingerprint is not None
        return self.player_legal.raw_source_fingerprint


class LiveDebugTwinTracker:
    """Pair debug and player-legal READY records without merging their payloads."""

    def __init__(self) -> None:
        self._records: dict[tuple[int, int, str], dict[str, LiveRecord]] = {}
        self._digests: dict[tuple[int, int, str, str], str] = {}
        self._current_twin: LiveDebugTwin | None = None

    @property
    def current_twin(self) -> LiveDebugTwin | None:
        return self._current_twin

    def clear(self) -> None:
        self._records.clear()
        self._digests.clear()
        self._current_twin = None

    def accept(self, record: LiveRecord) -> LiveDebugTwin | None:
        """Accept one READY semantic view and return a twin once both exist."""

        if record.record_type is not LiveRecordType.DECISION_READY:
            return None
        if record.information_profile not in {"player_legal", "omniscient_debug"}:
            return None
        assert record.battle_sequence is not None
        assert record.source_generation is not None
        assert record.raw_source_fingerprint is not None
        assert record.information_profile is not None

        key = (
            record.battle_sequence,
            record.source_generation,
            record.raw_source_fingerprint,
        )
        profile = record.information_profile
        digest_key = (*key, profile)
        digest = canonical_sha256(record.to_wire_dict())
        prior_digest = self._digests.get(digest_key)
        if prior_digest is not None and prior_digest != digest:
            raise ValueError(
                f"same debug-twin capture/profile changed payload: {key} {profile}"
            )

        bucket = self._records.setdefault(key, {})
        prior = bucket.get(profile)
        if prior is None:
            opposite = bucket.get(
                "omniscient_debug" if profile == "player_legal" else "player_legal"
            )
            if opposite is not None:
                self._require_shared_identity(opposite, record)
            bucket[profile] = record
            self._digests[digest_key] = digest

        legal = bucket.get("player_legal")
        debug = bucket.get("omniscient_debug")
        if legal is None or debug is None:
            return None
        twin = LiveDebugTwin(player_legal=legal, omniscient_debug=debug)
        self._current_twin = twin
        return twin

    @staticmethod
    def _require_shared_identity(left: LiveRecord, right: LiveRecord) -> None:
        fields = (
            "companion_version",
            "runtime_game_version",
            "ruleset_game_version",
            "ruleset_content_fingerprint",
            "mods",
            "kernel_identity",
            "battle_sequence",
            "source_generation",
            "raw_source_fingerprint",
        )
        mismatched = [
            name for name in fields if getattr(left, name) != getattr(right, name)
        ]
        if mismatched:
            joined = ", ".join(mismatched)
            raise ValueError(f"debug twin identity mismatch: {joined}")
