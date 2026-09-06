# Post-M1 companion capture substrate

Ticket #55 implements the smallest in-process Battle Brothers companion-mod
substrate needed before #57 canonical projection and affordance export. It is
not a tactical evaluator, transport implementation, advisor UI, or execution
layer.

## Frozen authority

The implementation follows the resolved post-M1 contracts from issues #50, #51
and #52. Runtime evidence is pinned to Battle Brothers Scripts revision
`162f498ac7c49b4c317bbf54718a595ecef6a65a`.

The key rule from #51 is that advice exists only during an explicit
**command-ready generation**. Capture is therefore a post-update observer, not a
turn-start hook. Losing readiness immediately produces an in-process
`DECISION_INVALIDATED` edge. Returning to the same unchanged semantic source is
an idempotent duplicate; returning to a changed source advances
`source_generation`.

## Mod layout

The repository-owned source tree is:

```text
companion_mod/
  scripts/
    !mods_preload/
      mod_bb_agent_capture.nut
    bb_agent/
      capture_substrate.nut
      hooks/
        tactical_state.nut
```

The preload file registers `mod_bb_agent_capture` with Modern Hooks and loads the
capture substrate plus the tactical-state hook. The hook wraps vanilla
`tactical_state.onInit`, `onUpdate`, `onBattleEnded`, and `onDestroy`; every
vanilla method is still invoked. No vanilla script file is replaced.

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

The implementation may become stricter after #58 real-game smoke evidence, but
must not loosen these guards merely to produce more snapshots.

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

Fingerprint inputs are stable string tokens over capture/ruleset provenance,
battle/turn/actor validation context, sorted mod identities, and sorted raw
actor source facts. The internal joined signature is used only for duplicate
comparison. It is intentionally **not** called the external
`raw_source_fingerprint`: #57 converts the stable inputs to the frozen SHA-256
fingerprint while constructing the exportable canonical payload.

The internal signature and raw fingerprint material are never written to the
normal log because they may encode hidden runtime facts.

## Legal observation memory

Raw truth and legal memory are separate stores. `CurrentRaw` contains rich
runtime acquisition references. `ObservationMemory` can be updated only through
the explicitly named `rememberPlayerLegalFact()` API, which #57 must call only
after a fact has already passed player-legal projection.

Memory is battle-local and is cleared on battle initialization/end. Hidden
runtime objects must never refresh remembered values. #57 remains responsible
for `ObservationPoint`, REMEMBERED/INFERRED/UNKNOWN semantics and the detailed
#52 field map.

## Diagnostics and failure behavior

The mod logs only non-sensitive capture lifecycle/health information: battle
sequence, generation, active actor ID, invalidation reason and generic capture
errors. It does not log raw actors, `CurrentProperties`, entity lists,
fingerprint material or observation-memory payloads.

Capture errors fail closed. If advice was READY, a capture failure invalidates
it immediately. The game-side observer never requires an external process, so
external absence/failure cannot block normal Battle Brothers play.

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

#57 owns projection plus affordance export; #58 owns real-game smoke and latency
evidence. This substrate alone does not authorize advisor promotion or execution.
