# Mechanics coverage and local rules authority

Issue #17 adds the versioned catalog/manifest substrate. `load_builtin_mechanics()`
loads package-owned JSON once at startup and returns a structured
`Result[MechanicsAuthority]`. Classification thereafter reads only the immutable
in-memory catalog and canonical state; no network, game install, toolkit process,
or reference refresh is involved.

## Shipped coverage

Every mandatory family is explicitly declared: ordinary attacks, movement,
AOO/disengagement, Wait, End Turn, equipment, Recover, reload, and other special
mechanics. The packaged manifest now declares the #18 ordinary-attack model and
the #19 deterministic transition families as supported; other control, AOE,
defensive, and special families remain `EVALUATION_UNSUPPORTED` until explicitly
implemented and tested.

The packaged `ordinary_attack` family is the deliberately narrow vanilla
`weapon.hand_axe` / `actives.chop` baseline. Its `ordinary-attack.v1` model uses
the independent regular and armor rolls in pinned `skill.nut:onScheduledTargetHit`,
then the armor/direct-damage sequence and final rounding in
`actor.nut:onDamageReceived`. The standard 25% head location and Chop's 1.5x head
multiplier come from the pinned scripts. Current displayed hit chance and AP/FAT
costs remain affordance previews and are applied exactly once. Any unmodelled
content, variant, effect, or unavailable target domain returns structured
unsupported coverage rather than falling back to this baseline.

The packaged `transitions.v1` family models resolved `MOVE_TO`, Wait, End Turn,
Recover, reload-like, and declared equipment transitions within the explicitly
supported M1 subset. Movement never repaths or invents a command: it consumes the
supplied resolved path and resolved costs. Contingent AOO reactions are source-
supplied path-scoped consequences, not enemy actions discovered by BB-Agent.
The transition evaluator validates supplied reactor/path geometry but does not
infer AOO capability from adjacency alone.

For a supported single-step disengagement, the resolved movement cost is paid for
the attempted step, all supplied contingent AOOs for that attempt may resolve,
and the step completes only on the all-miss branch. Any hit, lethal or not,
interrupts the step and leaves the mover on the pre-step tile; death may suppress
later reactions because the mover is no longer a living target. A supplied
reaction that cannot be evaluated by the narrow ordinary-attack model remains
coverage-incomplete.

A multi-step `MOVE_TO` carrying contingent AOO reactions is deliberately
`EVALUATION_UNSUPPORTED` in the current contract. The affordance contains only
aggregate path AP/FAT costs, while Battle Brothers applies movement costs
step-by-step; BB-Agent therefore does not invent partial costs for an early
interruption. Safe multi-step movement with no supplied contingent reaction may
still use the aggregate resolved command cost because the modeled path completes.
If broader interrupted multi-step support becomes necessary, the canonical
contract must first gain sufficient per-step cost authority rather than deriving
or guessing it inside the transition model.

`MechanicsAuthority.classify(state)` validates the state/freshness/completeness
and its exact ruleset identity, then returns one structural classification for
every affordance in stable action-ID order. A report records state/profile
identity, catalog fingerprint, manifest fingerprint, family dependencies, model
versions, and structured problems. Any structurally unsupported command yields
`INCOMPLETE_COVERAGE` while preserving the full report, including supported
candidates. It never drops a command, supplies a score, or returns a
recommendation.

Structural family coverage does not by itself establish that a particular
actor/target state can be evaluated. Model-specific checks may still reject
unsupported perks, effects, uncertainty, reaction context, item state, or other
inputs. Those failures must remain visible through the same structured result
boundary; a manifest declaration alone is not proof that every instance of the
family is evaluable.

Unknown skill IDs never fall back to an ordinary attack. Mappings distinguish
skill and item content, enforce action kind and the ordinary/self-skill target
shape, and reject unmodelled mode variants, extension parameters and custom
preview facts. EQUIP_ITEM resolves the actual inventory item's content; unknown
identity or undeclared slots remain unsupported. Movement structurally requires
the AOO family but the concrete contingent-reaction set comes from the fixture or
future adapter rather than inferred current-command legality.

## Catalog identity and provenance

The tiny static subset comes from `ninkjin/Battle-Brothers-Scripts` at commit
`162f498ac7c49b4c317bbf54718a595ecef6a65a`, the source pin already recorded by
#9. Each entry records its source path and full source blob SHA. It contains only
selected facts for `actives.chop`, `actives.recover`, `actives.reload_bolt`, and
`weapon.hand_axe`; it is not a complete vanilla catalog. Chop's additional head
modifier is recorded so it cannot be mistaken for a featureless basic attack.
The source's `split` skill is deliberately not included as ordinary: it is AOE.

The catalog schema, game/source identity, ordered mod set, provenance and entries
are hashed using canonical JSON SHA-256, excluding only the fingerprint field.
JSON object key order is irrelevant; array order belongs to artifact identity.
The manifest carries that content fingerprint, maps every catalog ID exactly
once, declares per-family effects/status/model version, and has its own computed
fingerprint. Missing declarations, duplicate mappings, unknown/cyclic
dependencies, absent AOO dependency, malformed provenance, unsupported schemas,
and fingerprints that disagree fail with structured validation problems.

Catalog changes require recomputing the catalog fingerprint and explicitly
updating the manifest and fixture ruleset. Manifest-only coverage/model changes
change its fingerprint. Neither loader attempts compatibility fallback.
Fingerprints detect mismatches, not authorship: artifact changes still require
source review and tests. Loaded value objects contain only frozen dataclasses,
tuples and scalars. Consumers should obtain them from the validating loaders,
not construct unchecked dataclass instances from external data.

The game version is explicitly the pinned script revision, not an inferred retail
build. Current affordability, AP/FAT/ammo/item costs, path and displayed hit
chance remain authoritative affordance inputs. Catalog base cost facts must
never replace or modify those resolved current costs.

## Resolution ownership

`ResolutionLedger.for_action_field(action, field)` binds each canonical resolved
cost, displayed hit chance, or displayed damage profile to its owning rules stage
and records the source authority. `apply(stage)` returns
`RESOLUTION_STAGE_CONFLICT` if that stage was already resolved or precedes an
already-completed stage. Later target mitigation and outcome stages remain
available without changing the originating preview authority. The immutable
ledger records each consumed stage for later traces.

Calculated inputs begin with `ResolutionLedger.calculated(model_version)` and
retain `BB_AGENT_RULES:<version>` authority. Opaque fields with no registered
stage, static values mislabeled as resolved previews, and debug-oracle inputs are
rejected at this production boundary. The ledger does not execute formulas; the
outcome/transition layers must preserve the same single-authority/no-double-
application contract when composing mechanics and later traces.

Focused regression coverage lives in `tests/test_mechanics.py`; authoritative PR
validation is provided by the repository's stable `tests`, `ruff`, and
`pyflakes` CI checks.
