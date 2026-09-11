# Full Combat Sandbox

Issue #102 provides the development-only full combat sandbox used to reproduce Battle Brothers tactical state offline.

## Purpose

The sandbox exists so Battle Brothers is not used as a hypothesis-by-hypothesis debugger. A live run should capture one complete tactical decision state, after which mechanics work can be developed and tested offline against that artifact and synthetic mutations of it.

This artifact is **omniscient debug data**. It is not a `player_legal` input and must never supply production action values or hidden information to normal decision output.

## Capture point and nonblocking requirement

The forensic snapshot is staged when the capture substrate produces a `DECISION_READY` generation. The tactical-state hook then calls `BBAGENT_CombatSandbox.pump()` before normal live export on each tactical `onUpdate`.

Only one bounded sandbox job is processed per update (`RecordsPerPump = 1`). Both discovery and serialization are incremental: raw-source inputs, actors, skills, items and tactical map squares are traversed by cursor jobs over successive updates. `begin()` only seeds those cursors and fixed metadata jobs; it never walks the complete roster or map synchronously.

Full actor/map breadth is preserved, but discovery, deep reflection, canonical JSON, SHA-256, Base64URL encoding and log emission are spread over many game updates instead of blocking one READY callback.

This nonblocking requirement is part of the contract. A synchronous full-map/full-actor discovery or dump in one callback is forbidden because it can freeze Battle Brothers.

Generation consistency comes from the capture substrate plus a forensic continuity guard. A failed normal `DECISION_READY` export may latch the unchanged production READY signature off, but the debug snapshot continues while command readiness and its original battle/source signature still match. If the actual battle/source generation or signature changes, the old forensic job is cancelled/superseded. Battle end, runtime incompatibility and tactical-state teardown also cancel any in-progress job.

The forensic pump runs before normal live export. Therefore a later affordance/export failure cannot prevent the debug dump from advancing or force the entire forensic snapshot into one game frame.

No extra `TimeUnit.Virtual` or `TimeUnit.Real` scheduler is used; the tactical update hook is the sole pump authority.

The result is generation-consistent forensic state, not an atomic dump of native engine memory. Script-readable objects are captured over successive updates while the same battle/source signature remains command-ready. For the intended workflow the user stops at a stable player decision while capture completes.

## Captured sections

The `BBCOMBAT1` stream contains independently hashed/chunked records for:

- `raw`: capture provenance, validation context, source generation and raw-source fingerprint metadata;
- `raw_fingerprint_input`: the complete raw-source fingerprint input list split into individual records;
- `tactical_state`: tactical-state parent metadata with large state split into field shards;
- `turn`: round, turn position, active runtime actor, current turn-sequence entity order, plus sharded turn-bar state;
- `entity_manager`: sharded script-readable entity-manager state and runtime fields;
- `tactical_global`: sharded `::Tactical` state;
- `navigator`: sharded script-readable navigator state;
- `navigator_settings`: the exact active-player movement settings constructed from the current actor;
- `constant`: Battle Brothers movement/direction/tactical/combat/item/skill/slot/body-part/morale constants used by the adapter, with large tables sharded by top-level field;
- `player_legal_meta`, `player_legal_tile`, and `player_legal_actor`: the complete player-legal projection split into bounded records for side-by-side comparison with debug truth;
- `observation_memory`: each current player-legal observation-memory fact;
- `actor_core`, `actor_state`, `actor_properties`, `actor_skills_container`, `actor_items_container`, `actor_ai`, `actor_skill`, and `actor_item`: full actor truth split into bounded records for every tactical actor returned by `Tactical.Entities.getAllInstances()`, including hidden enemies;
- `state_field`: independently bounded top-level fields belonging to heavy actor/global/container/tile/constant parent records;
- `state_scalar_pack`: bounded primitive fields grouped by owner so simple values do not consume one sandbox update each;
- `debug_probe`: single-purpose native-only observations such as the one-ally jump charging probe;
- `debug_movement_validation`: bounded DEBUG_ORACLE/native movement comparisons for exact-visible and remembered tiles;
- one `tile` parent record for every valid tactical map square, with properties and occupant internals sharded separately;
- `manifest_expected` shards plus `manifest`: provenance, counts, reflection limits, staging settings, and the complete expected-record set used by the extractor to reject incomplete captures.

## Actor records

Actor records collectively include, where script-readable:

- runtime and canonical IDs, name/title/type;
- faction, alliance to active actor, player-control flag, hidden-to-player flag;
- alive/placed/tile state;
- HP, armor, AP, fatigue, morale and initiative;
- wait/turn state;
- movement AP/fatigue tables, elevation costs and maximum traversable levels;
- sharded `actor.m` state;
- sharded current and base properties;
- sharded skills-container state plus each skill's ID, common queried properties and sharded `skill.m` state;
- sharded items-container state plus each item's ID, common queried properties and sharded `item.m` state;
- sharded AI-agent `m` state when available;
- ZOC/AoO state and allied factions when available.

Skill/item core records are built from lightweight getters only. They do not first recursively reflect `skill.m` or `item.m` and then discard it; those internal tables are touched only by their later field-shard jobs.

## Tile records

Each valid tactical tile parent record includes:

- canonical ID and square coordinates;
- elevation, terrain type and subtype;
- all six canonical neighbors;
- `IsEmpty`, `IsVisibleForPlayer`, and `IsDiscovered`;
- a reference summary for sharded tile `Properties`, including script-readable effects;
- current occupant identity where `getEntity()` exposes one, including hidden occupancy in this debug artifact, plus sharded occupant `m` state when readable.

## PLAYER_LEGAL and native movement validation

The sandbox freezes the independent `PLAYER_LEGAL` projection at the decision boundary, before any omniscient forensic job is processed. Its records are published only after the oracle work has completed. This separates computation from publication: mutable runtime references cannot silently change the projection's generation, and oracle values never feed the production projection.

After the deferred projection is available, DEBUG_ORACLE may enqueue a bounded validation plan. Production still uses zero native per-destination pathfinder calls. Native comparisons are diagnostic-only and are processed as ordinary sandbox jobs, so at most one native comparison runs in one tactical update.

The exact-visible validation plan is capped at six deterministic samples and may include:

- nearest reachable;
- farthest reachable;
- highest-cost reachable;
- ZOC entry;
- ZOC exit;
- a model-legal but resource-unreachable visible tile when present.

For each exact-visible sample, the artifact separates:

- graph legality (`model_legal`) from native `findPath` success;
- resource reachability (`model_reachable`) from native cost completion;
- modeled AP from native AP;
- modeled execution fatigue from independently reconstructed path-search fatigue, so native fatigue semantics are measured rather than assumed;
- modeled path tile count from the native cost object's tile count;
- modeled first/end endpoints from the native cost object's first/end endpoints.

The full ordered native path is not claimed when the script API does not expose it. Tile-count and endpoint comparisons are bounded geometry evidence for ZOC/AoO-relevant discrepancies, not a reconstruction of native A* internals.

Remembered-terrain validation reuses the sandbox's existing incremental `discover_tile` cursor. The cursor stores a DEBUG-only native-tile index as it already visits the map; no second synchronous full-map traversal is introduced. Once both tile discovery and PLAYER_LEGAL projection are complete, at most two remembered samples (`remembered_nearest` and `remembered_farthest`) are scheduled. They record native path/cost behavior while explicitly marking that production remembered-scope movement enumeration is not being inferred from oracle truth.

The single ally-jump `debug_probe` is also DEBUG-only. The observed live sample established that passing over one ally charges both constituent movement steps; production implements that rule from player-legal topology and owned-actor cost tables rather than reading the probe record.

## Reflective fidelity and bounds

The generic reflective dumper captures primitive, table and array data up to depth 6 and 512 entries per container, with a global 2048-node budget per top-level reflection. Any one logical record is capped at 32768 decoded bytes. Floats are preserved as explicit typed string values because the canonical live JSON encoder intentionally rejects raw floats. Nested native/script instances are represented with bounded state markers, and unsupported runtime values are represented by type markers, preventing object cycles and function graphs from making the snapshot unbounded.

Heavy script-readable objects are not reflected as one monolithic value. The fidelity layer creates a small parent record and emits each top-level field as its own `state_field` record. Each field therefore receives an independent 2048-node reflection budget, 32768-byte record cap, SHA-256 digest and chunk stream. The field record carries its owner section/key, original field-key type/text and ordinal so the structure can be reconstructed offline.

Duplicate actor/skill/item/turn collections that are already represented by dedicated records are emitted as explicit bounded references rather than recursively expanded a second time. Runtime/UI scaffolding fields may be summarized explicitly instead of being treated as missing state. Genuinely unique large structures such as strategic properties, actor constants and EntityManager strategies can be second-level sharded so nested entries receive independent reflection budgets. Large `StrategicProperties.Parties` entries are themselves sharded by party field, and AI `KnownOpponents` uses actor/tile/TTL references rather than recursively duplicating full actor graphs already present elsewhere in the artifact.

This sharding is used for tactical state, turn-bar state, entity-manager state/runtime fields, `::Tactical`, navigator state, configured constants, actor `m`, current/base actor properties, skills/items containers, AI state, individual skill/item `m`, tile properties and readable tile-occupant state.

A read failure for an individual ordinary record produces an explicit `__capture_error` record and capture continues. Discovery or transport failure cancels the generation rather than allowing the manifest to describe a silently incomplete full snapshot.

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

The user-facing extraction helper polls for a completed manifest instead of requiring the user to guess when staged capture has finished. On timeout it prints the latest sandbox progress/cancellation/error diagnostics.

After a complete snapshot is assembled, the extractor reports transport/fidelity defects separately from intentional compression:

- explicit `__capture_error` records;
- recursive `__bb_truncated` reflection markers;
- field-container iteration errors;
- PLAYER_LEGAL semantic inconsistencies, such as an active actor ID with no matching projected actor record;
- explicit reference-summary counts;
- explicit runtime-scaffolding-summary counts;
- nested-shard summary counts.

A manifest-complete snapshot can therefore be distinguished from a high-fidelity snapshot. Intentional reference/scaffolding/nested summaries are not silently counted as missing state, while actual truncation and semantic errors remain visible and inspectable.

The extracted JSON also carries top-level `extraction_metrics` derived from the Battle Brothers log. The current metric records the `player_legal_build_begin` and `player_legal_build_end` wall-clock timestamp buckets plus their coarse span in seconds. This is diagnostic timing evidence only; it is not part of the forensic manifest and does not affect player-legal state or movement values.

When movement validation records are present, the extractor also prints separate counters for:

- legality mismatches;
- resource-reachability mismatches;
- AP/FAT preview mismatches;
- execution-fatigue matches;
- path-search-fatigue matches;
- samples matching neither modeled fatigue semantic;
- modeled/native tile-count mismatches;
- modeled/native endpoint mismatches;
- remembered sample count and remembered native-found/native-complete counts.

## Validation

PR CI runs the normal `tests`, `ruff`, and `pyflakes` gates plus a Windows `squirrel-sourcecheck`. The sourcecheck downloads the exact `sq_taro.exe` compiler tracked by pinned BBBuilder commit `c71840e45801cce21da647a29945feabe4d0041e`, verifies the compiler binary size, and compiles every companion `.nut` file. This catches Battle Brothers Squirrel grammar errors without requiring a user-side BBBuilder run.

The installer independently rebuilds with the user's BBBuilder and refuses to install unless the preload contains the required projection, movement, sandbox discovery/fidelity/reference/nested/bounds/continuity, ally-jump probe, exact-visible movement-validation, fatigue-semantics, legality, geometry and remembered-validation layers. It also rejects stale superseded movement comparison/tie-break modules from the preload.

## Offline workflow

1. Install the exact full-combat sandbox build.
2. Enter one fresh combat and stop at the first active player brother.
3. Run `tools/extract_combat_snapshot.ps1`; it waits for a completed manifest and writes `combat-sandbox-latest.json`.
4. Read the printed quality and movement-validation summaries. Preserve/upload the resulting JSON artifact even if quality markers or comparison mismatches are nonzero so the exact gaps can be inspected. The JSON itself carries coarse PLAYER_LEGAL build timing metadata; preserve `log.html` only if extraction fails or finer log inspection is needed.
5. Build mechanics tests from the captured state and synthetic mutations offline.
6. Return to the live game only for mechanics that remain native-only after source and snapshot analysis.
