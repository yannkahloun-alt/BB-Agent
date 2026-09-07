# Full Combat Sandbox

Issue #102 provides the development-only full combat sandbox used to reproduce Battle Brothers tactical state offline.

## Purpose

The sandbox exists so Battle Brothers is not used as a hypothesis-by-hypothesis debugger. A live run should capture one complete tactical decision state, after which mechanics work can be developed and tested offline against that artifact and synthetic mutations of it.

This artifact is **omniscient debug data**. It is not a `player_legal` input and must never supply production action values or hidden information to normal decision output.

## Capture point and nonblocking requirement

The sandbox is started during `DECISION_READY` acquisition immediately after the player-legal projection is built and before affordance enumeration. Starting the forensic job must return immediately: the complete dump is emitted incrementally using `TimeUnit.Real` callbacks, initially one logical record per 8 ms slice.

This nonblocking requirement is part of the contract. A synchronous full-map/full-actor dump in the READY callback is forbidden because deep reflection, canonicalization, SHA-256, Base64URL encoding and log emission can freeze Battle Brothers.

The forensic job retains the original raw/projection references and is independent of later normal-capture readiness. Therefore a subsequent movement/path/affordance failure may invalidate normal `DECISION_READY` output without cancelling the already-started debug dump.

Before the manifest is committed, the job recomputes the capture substrate source fingerprint. If the source changed during the incremental dump, no manifest is emitted and the extractor rejects that generation as incomplete. The completed manifest records the matching initial/final fingerprints and the incremental capture mode.

`TimeUnit.Real` is used deliberately. The normal READY guard treats pending `TimeUnit.Virtual` events as gameplay activity; the diagnostic scheduler must not manufacture that condition.

## Captured sections

The `BBCOMBAT1` stream contains independently hashed/chunked records for:

- `raw`: capture provenance, validation context, source generation and raw-source fingerprint;
- `raw_input_batch`: the complete raw-source fingerprint input list split into bounded batches;
- `tactical_state` plus `tactical_state_field`: runtime identity and bounded reflective top-level state fields;
- `turn` plus `turn_state_field`: round, turn position, active runtime actor, current turn-sequence entity order, and bounded turn-bar fields;
- `entity_manager` plus `entity_manager_field`: runtime identity and bounded script-readable entity-manager fields;
- `constants`: Battle Brothers movement/direction/terrain constants and the exact active-player navigator settings constructed by the adapter;
- `player_legal`, `player_legal_tile`, and `player_legal_actor`: the complete player-legal projection split into bounded records for side-by-side comparison with debug truth;
- `observation_memory_entry`: each current player-legal observation-memory fact;
- `actor`, `actor_state`, `actor_current_properties`, `actor_base_properties`, `actor_skills_container`, `actor_items_container`, `actor_ai`, `actor_skill`, and `actor_item`: full actor truth split into bounded records for every tactical actor returned by `Tactical.Entities.getAllInstances()`, including hidden enemies;
- one `tile` record for every valid tactical map square;
- `manifest`: provenance, counts, reflection limits, incremental-capture settings, consistency fingerprints, and the complete expected-record list used by the extractor to reject incomplete captures.

## Actor records

Actor records collectively include, where script-readable:

- runtime and canonical IDs, name/title/type;
- faction, alliance to active actor, player-control flag, hidden-to-player flag;
- alive/placed/tile state;
- HP, armor, AP, fatigue, morale and initiative;
- wait/turn state;
- movement AP/fatigue tables, elevation costs and maximum traversable levels;
- full bounded `actor.m` state;
- current and base properties;
- skills-container state plus each skill's ID, common queried properties and bounded `skill.m` state;
- items-container state plus each item's ID, common queried properties and bounded `item.m` state;
- AI-agent `m` state when available;
- ZOC/AoO state and allied factions when available.

## Tile records

Each valid tactical tile record includes:

- canonical ID and square coordinates;
- elevation, terrain type and subtype;
- all six canonical neighbors;
- `IsEmpty`, `IsVisibleForPlayer`, and `IsDiscovered`;
- bounded tile `Properties`, including script-readable effects;
- current occupant identity/state where `getEntity()` exposes one, including hidden occupancy in this debug artifact.

## Reflective state

The generic reflective dumper captures primitive, table and array data up to depth 6 and 512 entries per container. Floats are preserved as explicit typed string values because the canonical live JSON encoder intentionally rejects raw floats. Nested native/script instances and unsupported runtime values are represented by type markers instead of being recursively traversed, preventing object cycles and function graphs from making the snapshot unbounded.

## Transport and integrity

Large log lines are unsafe in Battle Brothers. Each record is therefore canonicalized independently and emitted as `BBCOMBAT1` chunks with:

- battle sequence;
- source generation;
- section and key;
- chunk index/count;
- decoded byte length;
- SHA-256 digest;
- Base64URL payload chunk.

Each chunk payload is at most 1200 characters. The Python extractor reassembles records, verifies lengths and SHA-256 digests, then verifies the manifest's expected-record set before writing the standalone JSON sandbox.

The user-facing extraction helper polls for a completed manifest instead of requiring the user to guess when incremental capture has finished.

## Offline workflow

1. Install the exact full-combat sandbox build.
2. Enter one fresh combat and stop at the first active player brother.
3. Run `tools/extract_combat_snapshot.ps1`; it waits for the completed manifest and writes `combat-sandbox-latest.json`.
4. Preserve/upload the resulting JSON artifact.
5. Build mechanics tests from the captured state and synthetic mutations offline.
6. Return to the live game only for mechanics that remain native-only after source and snapshot analysis.
