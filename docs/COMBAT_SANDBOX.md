# Full Combat Sandbox

Issue #102 provides the development-only full combat sandbox used to reproduce Battle Brothers tactical state offline.

## Purpose

The sandbox exists so Battle Brothers is not used as a hypothesis-by-hypothesis debugger. A live run should capture one complete tactical decision state, after which mechanics work can be developed and tested offline against that artifact and synthetic mutations of it.

This artifact is **omniscient debug data**. It is not a `player_legal` input and must never supply production action values or hidden information to normal decision output.

## Capture point

The sandbox is emitted during `DECISION_READY` acquisition before affordance enumeration. Therefore a later movement/path/affordance failure does not prevent the combat snapshot from being written.

## Captured sections

The `BBCOMBAT1` stream contains independently hashed/chunked records for:

- `raw`: capture provenance, validation context, source generation, raw-source fingerprint inputs and fingerprint;
- `tactical_state`: bounded reflective dump of the tactical state's script-readable `m` state;
- `turn`: round, turn position, active runtime actor, current turn-sequence entity order, and bounded turn-bar state;
- `entity_manager`: bounded script-readable entity-manager state;
- `constants`: Battle Brothers movement/direction/terrain constants and the exact active-player navigator settings constructed by the adapter;
- `player_legal`: the complete player-legal projection for side-by-side comparison with debug truth;
- `observation_memory`: current player-legal observation memory;
- one `actor` record for every tactical actor returned by `Tactical.Entities.getAllInstances()`, including hidden enemies;
- one `tile` record for every valid tactical map square;
- `manifest`: provenance, counts, reflection limits, and the complete expected-record list used by the extractor to reject incomplete captures.

## Actor records

Each actor record includes, where script-readable:

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

## Offline workflow

1. Capture one fresh combat decision with DEBUG_ORACLE enabled.
2. Run `tools/extract_combat_snapshot.py` against `log.html`.
3. Preserve/upload the resulting JSON artifact.
4. Build mechanics tests from the captured state and synthetic mutations offline.
5. Return to the live game only for mechanics that remain native-only after source and snapshot analysis.
