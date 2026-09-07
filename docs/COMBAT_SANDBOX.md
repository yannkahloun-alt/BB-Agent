# Full Combat Sandbox

Issue #102 provides the development-only full combat sandbox used to reproduce Battle Brothers tactical state offline.

## Purpose

The sandbox exists so Battle Brothers is not used as a hypothesis-by-hypothesis debugger. A live run should capture one complete tactical decision state, after which mechanics work can be developed and tested offline against that artifact and synthetic mutations of it.

This artifact is **omniscient debug data**. It is not a `player_legal` input and must never supply production action values or hidden information to normal decision output.

## Capture point and nonblocking requirement

The forensic snapshot is staged when the capture substrate produces a `DECISION_READY` generation. The tactical-state hook then calls `BBAGENT_CombatSandbox.pump()` before normal live export on each tactical `onUpdate`.

Only one bounded logical record is processed per update (`RecordsPerPump = 1`). Full actor/map breadth is preserved, but deep reflection, canonical JSON, SHA-256, Base64URL encoding and log emission are spread over many game updates instead of blocking one READY callback.

This nonblocking requirement is part of the contract. A synchronous full-map/full-actor dump in one callback is forbidden because it can freeze Battle Brothers.

Generation consistency comes from the normal capture substrate. Every tactical update observes the live state first. If that observation advances battle/source generation, the old forensic job is cancelled/superseded before it can complete. Battle end, runtime incompatibility and tactical-state teardown also cancel any in-progress job.

The forensic pump runs before normal live export. Therefore a later affordance/export failure cannot force the entire forensic dump into one frame. Repeated READY observations of the same unchanged generation allow the staged dump to continue advancing across tactical updates.

No extra `TimeUnit.Virtual` or `TimeUnit.Real` scheduler is used; the tactical update hook is the sole pump authority.

## Captured sections

The `BBCOMBAT1` stream contains independently hashed/chunked records for:

- `raw`: capture provenance, validation context, source generation and raw-source fingerprint metadata;
- `raw_fingerprint_input`: the complete raw-source fingerprint input list split into individual records;
- `tactical_state`: bounded reflective tactical-state script data;
- `turn`: round, turn position, active runtime actor, current turn-sequence entity order, and bounded turn-bar state;
- `entity_manager`: bounded script-readable entity-manager state;
- `tactical_global`: bounded reflective `::Tactical` state;
- `navigator`: bounded script-readable navigator state;
- `navigator_settings`: the exact active-player movement settings constructed from the current actor;
- `constant`: Battle Brothers movement/direction/tactical/combat/item/skill/slot/body-part/morale constants used by the adapter;
- `player_legal_meta`, `player_legal_tile`, and `player_legal_actor`: the complete player-legal projection split into bounded records for side-by-side comparison with debug truth;
- `observation_memory`: each current player-legal observation-memory fact;
- `actor_core`, `actor_state`, `actor_properties`, `actor_skills_container`, `actor_items_container`, `actor_ai`, `actor_skill`, and `actor_item`: full actor truth split into bounded records for every tactical actor returned by `Tactical.Entities.getAllInstances()`, including hidden enemies;
- one `tile` record for every valid tactical map square;
- `manifest_expected` shards plus `manifest`: provenance, counts, reflection limits, staging settings, and the complete expected-record set used by the extractor to reject incomplete captures.

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

The generic reflective dumper captures primitive, table and array data up to depth 6 and 512 entries per container. Floats are preserved as explicit typed string values because the canonical live JSON encoder intentionally rejects raw floats. Nested native/script instances are represented with bounded state markers, and unsupported runtime values are represented by type markers, preventing object cycles and function graphs from making the snapshot unbounded.

## Transport and integrity

Large log lines are unsafe in Battle Brothers. Each record is canonicalized independently and emitted as `BBCOMBAT1` chunks with:

- battle sequence;
- source generation;
- section and key;
- chunk index/count;
- decoded byte length;
- SHA-256 digest;
- Base64URL payload chunk.

Each chunk payload is at most 1200 characters. The Python extractor reassembles records, verifies lengths and SHA-256 digests, reconstructs the manifest expected-record shards, and rejects incomplete captures before writing the standalone JSON sandbox.

The user-facing extraction helper polls for a completed manifest instead of requiring the user to guess when staged capture has finished.

## Offline workflow

1. Install the exact full-combat sandbox build.
2. Enter one fresh combat and stop at the first active player brother.
3. Run `tools/extract_combat_snapshot.ps1`; it waits for a completed manifest and writes `combat-sandbox-latest.json`.
4. Preserve/upload the resulting JSON artifact.
5. Build mechanics tests from the captured state and synthetic mutations offline.
6. Return to the live game only for mechanics that remain native-only after source and snapshot analysis.
