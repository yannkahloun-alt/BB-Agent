# Post-M1 companion capture substrate

Ticket #55 implements the smallest in-process Battle Brothers companion-mod
substrate needed before #57 canonical projection and affordance export. It is
not a tactical evaluator, transport implementation, advisor UI, or execution
layer.

## Frozen authority

The implementation follows the resolved post-M1 contracts from issues #50, #51
and #52. Runtime evidence is pinned to Battle Brothers Scripts revision
`162f498ac7c49b4c317bbf54718a595ecef6a65a`, whose source import identifies the
running baseline as Battle Brothers `1.5.2.2`.

The key rule from #51 is that advice exists only during an explicit
**command-ready generation**. Capture is therefore a post-update observer, not a
turn-start hook. Losing readiness immediately produces an in-process
`DECISION_INVALIDATED` edge. Returning after invalidation to the same unchanged
semantic source is an idempotent duplicate READY on the same generation;
uninterrupted command-ready update ticks emit no duplicate lifecycle event.
Returning to a changed source advances `source_generation`.

## Mod layout

The repository-owned source tree is:

```text
companion_mod/
  scripts/
    !mods_preload/
      mod_bb_agent_capture.nut
    bb_agent/
      capture_substrate.nut
      affordance_source_identity.nut
      observation_memory.nut
      runtime_provenance.nut
      hooks/
        tactical_state.nut
```

The preload file registers `mod_bb_agent_capture` with Modern Hooks and loads the
capture substrate, affordance-source identity hardening, legal
observation-memory boundary, runtime-provenance gate, and tactical-state hook.
The hook wraps vanilla `tactical_state.onInit`, `onUpdate`, `onBattleEnded`, and
`onFinish`; every vanilla method is still invoked. `onFinish` is the supported
state teardown lifecycle inherited from `scripts/states/state`; the companion
does not attempt to wrap a nonexistent `onDestroy` method. No vanilla script
file is replaced.

## Runtime provenance and compatibility

The selected static rules/content identity is the pinned scripts revision plus
content fingerprint
`4c4b714832d1989740a6f07dce058c11aa1e9123056966ede06ce42d1df182bd`.
That selected identity is not treated as proof of the running game.

`runtime_provenance.nut` separately probes the live process using supported
runtime authorities:

- `GameInfo.getVersionNumber()` for the actual Battle Brothers version;
- `Const.Serialization.Version` as an additional runtime compatibility fact;
- `Hooks.getMods()` plus each mod object's version for the normalized live
  registered-mod stack;
- `BBAGENT_Mod.Version` as the explicit companion version consumed later by
  #57/#56 rather than requiring mod-stack string parsing.

The initial supported runtime is exactly Battle Brothers `1.5.2.2` plus the
base `vanilla` registration, official DLC registrations, Modern Hooks, and the
BB-Agent capture mod itself. Any different game version or additional
unrecognized mod registration is conservatively `runtime_incompatible`.
Overhaul/content mods are therefore never silently assigned the selected vanilla
ruleset fingerprint.

Runtime provenance is refreshed when a tactical battle initializes. The raw
acquisition provenance records companion version, actual game version,
serialization version, full sorted `id@version` mod identities, selected
scripts/ruleset identity, unsupported mod IDs, compatibility verdict, and
incompatibility reason. An incompatible process never calls the capture
observer; if advice had somehow been READY it is invalidated immediately, and
`LastError` records a visible generic runtime incompatibility reason.
Runtime-probe exceptions are contained inside the provenance gate, converted to
`runtime_provenance_error`, and disable capture instead of escaping into vanilla
tactical initialization. A later successful compatibility refresh clears that
stale provenance health error. Normal Battle Brothers play continues unaffected.

`configureProvenance()` remains as an optional stricter #57 validation hook. It
may require an exact expected runtime mod-identity list, but it cannot override
the built-in game-version/unsupported-mod gate. Its exact expectation is stored
persistently and re-applied by every later runtime refresh, including battle
initialization; an explicit mismatch invalidates any currently READY decision
without waiting for the next tactical update.

## Command-ready predicate

`BBAGENT_Capture._commandReadiness()` fails closed unless all frozen #51 guards
hold:

- tactical state exists, battle is not ended, and the game is not paused;
- a turn-sequence active entity exists;
- the actor is alive, placed, player-controlled, turn-started and not turn-done;
- tactical input is unlocked;
- `CurrentActionState` is null;
- the actor skill container is not busy;
- the navigator is not travelling the active actor;
- no virtual-time event remains scheduled;
- known flee/exit modal tactical states are absent.

Runtime compatibility is an outer gate before this observer runs. The
implementation may become stricter after #58 real-game smoke evidence, but must
not loosen these guards merely to produce more snapshots.

## In-process raw acquisition API

`::BBAGENT_Capture.getCurrentRawAcquisition()` exposes one narrow in-process
object only while the current generation is READY. It contains:

- capture contract and source provenance;
- battle sequence and source generation;
- round, turn position, active actor ID, waited and turn-start validation facts;
- deterministic `RawSourceFingerprintInputs`;
- references to the active actor, tactical state, turn-sequence bar, entity
  manager, and navigator.

These rich runtime references deliberately stay inside Battle Brothers. Ticket
#55 does **not** serialize them to `log.html` or any other external output. #57
must read this API, perform the frozen #52 information-policy projection in
process, construct the complete current affordance set, and only then emit the
normal player-legal live envelope.

## Semantic source generation

The companion mod does not call `Math.rand()` or other gameplay RNG for capture
identity. `battle_sequence` increments when a tactical state initializes.
Within one battle, `source_generation` starts at `-1` and increments when a
newly command-ready deterministic source signature differs from the prior READY
signature.

Fingerprint inputs are stable string tokens over runtime/capture/ruleset
provenance, battle/turn/actor validation context, sorted mod identities, sorted
raw actor source facts, current turn-sequence order, current active-player
skill-affordance authority, and deterministic tactical-map tile facts. Primitive
skill/item/current-property state remains an in-process raw source for all
actors; resolved `queryActives()` usability/affordability/AP/FAT/target metadata
is queried only for the command-ready active player actor. Wait authority,
movement-cost state, and the active actor's allied-faction set are also part of
the source signature.

`affordance_source_identity.nut` strengthens the raw identity where #53 command
semantics depend on structure that broad object fields do not encode:

- active-player item-container slot **position** topology is fingerprinted using
  slot index, position, empty/blocked sentinel, item content ID, item condition,
  and primitive item state. This prevents two bag positions from changing
  EQUIP_ITEM source/target/displacement semantics while retaining the same broad
  `CurrentSlotType`;
- tactical tile effects are included in the existing single map scan using only
  stable primitive fields such as effect type/lifetime/flags. Callback functions
  and opaque engine objects are ignored;
- no equip/swap/action-cost payment, skill use, movement, Wait, End Turn, RNG, or
  tile-effect mutation is called to build these tokens.

Map tokens cover valid tile coordinates, elevation, terrain type/subtype,
empty/occupied state, player visibility and discovery state, plus primitive
tile-effect state. This prevents a map/turn/affordance-source change that #57 may
consume from silently reusing a prior generation.

The internal joined signature is used only for duplicate comparison. It is
intentionally **not** called the external `raw_source_fingerprint`: #57 converts
the stable inputs to the frozen SHA-256 fingerprint while constructing the
exportable canonical payload.

The internal signature and raw fingerprint material are never written to the
normal log because they may encode hidden runtime facts.

## Legal observation memory

Raw truth and legal memory are separate stores. `CurrentRaw` contains rich
runtime acquisition references. `ObservationMemory` can be updated only through
the explicitly named `rememberPlayerLegalFact()` API, which #57 must call only
after a fact has already passed player-legal projection.

`observation_memory.nut` hardens this API boundary. Stored values must be
JSON-like player-legal data: null/bool/integer/float/string values, arrays of
those values, or string-keyed tables recursively composed from those values.
Runtime instances, functions, weak references and other opaque engine objects
are rejected. Accepted values are deep-copied on write, and
`getObservationMemory()` returns a detached deep copy, so callers cannot mutate
the internal legal-memory store through an input or returned reference.
Observation coordinates are constrained to non-negative integer round/decision
indices matching the canonical `ObservationPoint` domain.

Memory is battle-local and is cleared on battle initialization/end. Hidden
runtime objects must never refresh remembered values. #57 remains responsible
for REMEMBERED/INFERRED/UNKNOWN semantics and the detailed #52 field map.

## Diagnostics and failure behavior

The mod logs only non-sensitive capture lifecycle/health information: battle
sequence, generation, active actor ID, invalidation reason, runtime compatibility
reason/version, and generic capture errors. It does not log raw actors,
`CurrentProperties`, entity lists, fingerprint material or observation-memory
payloads.

Capture and compatibility errors fail closed. If advice was READY, a capture or
provenance failure invalidates it immediately. The game-side observer never
requires an external process, so external absence/failure cannot block normal
Battle Brothers play; runtime-provenance probe failures are also contained
rather than propagated into the vanilla tactical lifecycle.

## Explicit non-goals / prohibited paths

Ticket #55 contains no calls that:

- move through the navigator;
- activate a skill;
- swap/use items;
- Wait or End Turn;
- synthesize mouse/keyboard input;
- mutate AP, fatigue, turn order, selection or path state for capture;
- consume Battle Brothers gameplay RNG for IDs;
- perform tactical evaluation inside the game;
- generically serialize hidden actor/current-property/object graphs.

#57 owns projection plus affordance export; #58 owns real-game compile, oracle,
and latency evidence. This substrate alone does not authorize advisor promotion
or execution.
