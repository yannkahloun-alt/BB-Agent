# Post-M1 live canonical projection and affordance export

Ticket #57 connects the merged #55 in-process capture substrate to the merged #56
strict live-envelope receiver. It is an observation/export adapter only. It does
not evaluate tactics and contains no command-execution path.

## Boundary

The normal live path is:

```text
Battle Brothers runtime
  -> #55 rich in-process raw acquisition
  -> #57 player_legal projection
  -> #57 complete current ActionAffordanceSet acquisition
  -> canonical state/action identity
  -> BBAGENT1 READY / INVALIDATED records
  -> #56 strict external ingest
  -> #57 host raw_capture_id binding + unchanged TacticalState validator
  -> closed M1 decision kernel
```

Rich raw runtime objects never cross the normal transport boundary. The only
normal READY payload is `information_profile=player_legal`.

## Companion version and modules

The companion version is `0.2.0` for the canonical-export implementation. The
Modern Hooks preload order is intentionally explicit:

```text
capture_substrate.nut
affordance_source_identity.nut
observation_memory.nut
runtime_provenance.nut
canonical_wire.nut
player_legal_projection.nut
player_legal_hardening.nut
canonical_identity.nut
affordance_export.nut
live_export.nut
hooks/tactical_state.nut
```

The first four modules are the #55 substrate. The following five implement #57,
and the tactical hook emits lifecycle records only after every dependency is
loaded.

## Player-legal projection

`player_legal_projection.nut` implements the frozen #52 boundary field by
field.

Player-owned brothers expose exact player-visible current resources, equipment,
active skills/effects and displayed tactical stats. Visible non-owned actors do
not export raw HP/AP/FAT/armor/stat values; those fields remain `UNKNOWN` until a
player-visible coarse mapping is explicitly implemented. Never-seen hidden
actors are omitted.

A visible hostile contributes only legal observation memory. Once it is hidden,
its current position is `UNKNOWN`; `last_seen` contains only its prior observed
tile and observation point. Hidden raw runtime state never refreshes that
memory.

Map topology is canonicalized in-process. Current tile semantic state is emitted
only for player-visible tiles. Previously visible tiles may remain through the
battle-local legal memory with remembered terrain/effect observations. Hidden
current occupancy is never copied from raw runtime state. The additional
`player_legal_hardening.nut` wrapper makes the turn presentation conservative:
hidden raw actors are omitted without leaving raw sequence-number gaps or
consuming the emitted turn-list limit.

Environment/ground semantics not needed by the current M1 subset use their
frozen conservative fallbacks (`light=unknown`, no generic ground-object dump).

## Complete current affordances

`affordance_export.nut` follows the frozen #53 command authorities. A READY
snapshot is exported as `COMPLETE` only when every enumerator finishes and every
current executable command it discovers can be represented truthfully.

### Skills

The adapter starts from `active.getSkills().queryActives()` and keeps only skills
that are currently `isUsable()` and `isAffordable()`. Targeted skills are probed
with the game's own `isUsableOn(tile, active.getTile())` authority over
player-visible targetable tiles. Resolved AP/FAT costs come directly from the
current skill getters. Player-visible hit chance uses the same game getter the
normal targeting UI exposes. AOE affected-tile preview is emitted only when all
reported affected tiles are already in the player-legal projection.

Ammo/resource cost is not guessed from method names. When a legal skill consumes
ammo, the adapter resolves the current player-visible ammo source and requires an
explicit integer `getAmmoCost()` value. Unsupported consumable/charge semantics
fail acquisition rather than becoming zero.

### Movement

MOVE_TO uses the player's native tactical navigator and the same movement
settings used by vanilla tactical path selection. The adapter queries one path
per visible destination, reads the resolved game path and AP/FAT costs, then
clears temporary navigator path/visualization state before export. It never
starts travel.

Because the exact native path container is a runtime engine seam rather than a
Squirrel class in the pinned scripts dump, the extractor accepts only documented
read-only path shapes and otherwise fails the snapshot. #58 must prove the
selected path/costs match the real player preview.

Visible disengagement/ZOC reactions are preserved as contingent AOO reactions.
Player-legal mode does not manufacture hidden hit probabilities. When exact odds
are unavailable, the reaction carries the explicit unsupported mechanic
`live.player_legal.aoo_probability_unavailable`; the closed kernel can then
surface `INCOMPLETE_COVERAGE` without losing the legal move.

### Wait, End Turn and equipment

Wait is present only when both turn-bar and actor wait authority allow it. End
Turn is always included for a command-ready active player actor. Both have exact
zero costs.

In-combat equipment candidates are built without calling `equip`, `unequip`,
`swap` or `payForAction`. The adapter uses the same tactical character-screen
pure query helpers plus `item_container.isActionAffordable()` and
`getActionCost()`. The switch AP cost is placed in canonical `ap_cost`; the
separate `item_action_cost` remains zero because the current M1 transition model
charges the actor's AP once and no second item resource is demonstrated.
Two-displaced-item cases that cannot be represented by the current canonical
shape fail the snapshot instead of silently disappearing. #58 remains the
required real-game zero-false-positive/negative oracle for this provisional
inventory enumerator.

## Canonical identity

`canonical_identity.nut` reproduces the existing Python M1 identities rather
than introducing adapter IDs.

- `action_id` hashes exactly the existing command-intent fields.
- normalization sorts extension parameters/preview facts and affected-tile sets.
- `state_id` excludes the same transport/provenance/resolution-authority fields
  as `TacticalState._identity_dict()`.
- all state/actions share `source_generation=live:<battle>:<generation>`.

The producer leaves `raw_capture_id=null`: the host cannot know the final stream
identity until #56 accepts the record.

## Framing and host validation

`canonical_wire.nut` implements the frozen `BBAGENT1` record framing with
canonical sorted-key JSON, SHA-256 and unpadded base64url. The v1 live producer
rejects floats rather than risking Python/Squirrel formatting drift; current
live fields use exact integers or explicit UNKNOWN representations where a
floating uncertainty value is not required.

`live_export.nut` emits only the strict #56 schemas:

- `STREAM_START` at tactical battle initialization;
- `DECISION_READY` after successful player-legal projection + complete
  affordance acquisition;
- `DECISION_INVALIDATED` for readiness loss or a capture fault.

READY acquisition is transactional. Immediately before export, the companion
rechecks battle/source generation and hashes the current #55 raw fingerprint
inputs again. Any mismatch aborts the READY and emits a generic `capture_fault`
invalidation. Decoded records are capped at 2 MiB and full encoded frames at
3 MiB, matching #56 defaults.

On the host, `materialize_live_tactical_state()` recursively thaws #56's frozen
payload, requires the producer to have left `raw_capture_id` null, binds the
accepted host-generated capture ID, and then calls the unchanged
`TacticalState.from_dict()` validator. It additionally checks information
profile, ruleset identity, battle/source generation, and every affordance
source-generation label against the accepted envelope. The M1 kernel therefore
never receives an accepted live payload that skipped canonical validation.

## Failure domains

`AFFORDANCE_ACQUISITION_FAILURE` is represented game-side as a capture fault: no
partial command set is exported and the external kernel is not invoked for that
READY generation.

`INCOMPLETE_COVERAGE` is different: the adapter successfully supplied a complete
truthful current command set, but one or more legal mechanics are outside the
closed M1 evaluation manifest. That complete state is valid input and the kernel
owns the explicit coverage failure.

Transport/version/mod mismatches remain #56 compatibility failures.

## Prohibited paths

The #57 producer contains no command execution or input automation. In
particular it does not call skill use/onUse, navigator travel, item equip/swap or
cost payment, Wait, End Turn, mouse/keyboard automation, or gameplay RNG merely
to enumerate/export commands. Temporary navigator query state is cleared before
READY transport.

## Validation split

CI for #57 can validate Python materialization, exact contract literals, module
ordering, no-cheat/no-execution source boundaries and all existing M1 tests. It
cannot prove Battle Brothers runtime compilation or native navigator/inventory
oracle fidelity.

Ticket #58 is therefore the first real-game adapter promotion gate. It must
verify the installed `0.2.0` companion against actual player-selectable commands,
including supported and unsupported skills, ranged hit chance, multiple moves,
ZOC, Wait/Wait-spent, End Turn, blocked/two-hand equipment swaps, ammo/reload,
deliberate acquisition failure, stale/invalidation behavior, and zero
player-legal debug leakage. Until #58 returns `ADAPTER READY FOR SHADOW`, this
implementation is not a shadow/advisor release gate and authorizes no execution.
