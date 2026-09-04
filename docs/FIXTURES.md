# Fixture and replay inputs

M1 fixtures use the versioned `bb-agent-fixture.v1` JSON envelope implemented
in `bb_agent.fixtures`. The envelope keeps three concerns separate:

- `state` is the canonical `TacticalState` and includes its validated semantic
  state ID and complete current `ActionAffordanceSet`;
- `metadata` records the stable fixture ID, source, taxonomy, severity,
  rules/content fingerprint, information profile, completeness declaration,
  review status, and provenance;
- `expectations` and `oracle_annotations` are fixture-harness data. They do not
  participate in the tactical state ID or replay decision identity.

`load_fixture` and `save_fixture` return structured `Result` values. Malformed
JSON, unsupported schema versions, stale hashes/affordances, and metadata/state
mismatches are reported with fixture-specific error codes and JSON paths.

Call `FixtureEnvelope.replay_input()` to obtain the ranking input for later
decision APIs. It contains the normalized state, profile, and rules/content
fingerprint, while deliberately removing non-identity fixture annotations.
Canonical omniscient-debug action data remains present in debug replay states;
player-legal state validation forbids it. Use `validate_fixture_pair` for
`player_legal` / `omniscient_debug`
views that must share a nonempty `raw_capture_id` and retain distinct state IDs.

The handcrafted examples in `tests/fixtures/ticket_16` demonstrate a
player-legal state with unknown enemy resources but a legitimate resolved hit
chance preview, together with its linked omniscient diagnostic view.
