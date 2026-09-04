# Mechanics coverage and local rules authority

Issue #17 adds the versioned catalog/manifest substrate, not combat outcomes.
`load_builtin_mechanics()` loads package-owned JSON once at startup. It returns a
structured `Result[MechanicsAuthority]`. Classification thereafter reads only
the immutable in-memory catalog and canonical state; no network, game install,
toolkit process, or reference refresh is involved.

## Shipped coverage

Every mandatory family is explicitly declared: ordinary attacks, movement,
AOO/disengagement, Wait, End Turn, equipment, Recover, reload, and other special
mechanics. Families remain `EVALUATION_UNSUPPORTED` until their downstream
outcome/transition ticket implements and tests them; model versions are null
for unsupported families and their reason names the pending work.
Apart from the explicitly supported ordinary-attack model below, the test suite
uses temporary declarations with `test-validation-stub.v1` to exercise positive
coverage paths. These are not packaged production models.

The packaged `ordinary_attack` family is the deliberately narrow vanilla
`weapon.hand_axe` / `actives.chop` baseline. Its `ordinary-attack.v1` model uses
the independent regular and armor rolls in pinned `skill.nut:onScheduledTargetHit`,
then the armor/direct-damage sequence and final rounding in
`actor.nut:onDamageReceived`. The standard 25% head location and Chop's 1.5x
head multiplier come from the pinned scripts. Current displayed hit chance and
AP/FAT costs remain affordance previews and are applied exactly once. Any
unmodelled content, variant, effect, or unavailable target domain returns
structured unsupported coverage rather than falling back to this baseline.

`MechanicsAuthority.classify(state)` validates the state/freshness/completeness
and its exact ruleset identity, then returns one classification for every
affordance in stable action-ID order. A report records state/profile identity,
catalog fingerprint, manifest fingerprint, family dependencies, model versions,
and structured problems. Any unsupported command yields `INCOMPLETE_COVERAGE`
while preserving the full report, including supported candidates. It never
drops a command, supplies a score, or returns a recommendation. There is no
diagnostic exemption in this first API: all supplied commands count.

This is structural family coverage. It does not establish that actor/target
perks, effects, uncertainty, or every item state can be evaluated. Before
activating a production family, #18/#19 must implement model-specific input and
state-mechanics checks and propagate their failures through the same coverage
result. A manifest declaration alone is not an outcome implementation.

Unknown skill IDs never fall back to an ordinary attack. Mappings distinguish
skill and item content, enforce action kind and the ordinary/self-skill target
shape, and reject unmodelled mode variants, extension parameters and custom
preview facts. EQUIP_ITEM resolves the actual inventory item's content; unknown
identity, undeclared slots, and displacement remain unsupported. Movement
conservatively requires the AOO family for every path at this substrate stage.
It does not infer ZOC triggers or generate alternative routes. #19 owns supported
trigger/outcome semantics, including cases where movement can be shown safe.

## Catalog identity and provenance

The tiny static subset comes from `ninkjin/Battle-Brothers-Scripts` at commit
`162f498ac7c49b4c317bbf54718a595ecef6a65a`, the source pin already recorded by #9.
Each entry records its source path and full source blob SHA. It contains only
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

The game version is explicitly the pinned script revision, not an inferred
retail build. Current affordability, AP/FAT/ammo/item costs, path and displayed
hit chance remain authoritative affordance inputs. Catalog base cost facts must
never replace or modify those resolved current costs. Recover division and
reload's additional state changes still need exact transition semantics in #19;
the static fields are not executable formulas.

## Resolution ownership

`ResolutionLedger.for_action_field(action, field)` binds each canonical resolved
cost, displayed hit chance, or displayed damage profile to its owning rules
stage and records the source authority. `apply(stage)` returns
`RESOLUTION_STAGE_CONFLICT` if that stage was already resolved or precedes an
already-completed stage. Later target mitigation and outcome stages remain
available without changing the originating preview authority. The immutable
ledger records each consumed stage for later traces.

Calculated inputs begin with `ResolutionLedger.calculated(model_version)` and
retain `BB_AGENT_RULES:<version>` authority. Opaque fields with no registered
stage, static values mislabeled as resolved previews, and debug-oracle inputs
are rejected at this production boundary. The ledger does not execute formulas;
#18/#19 must use it when composing formulas and carry it into outcome traces.

Run the repository's normal pytest, Ruff and Pyflakes gates. Focused regression
coverage lives in `tests/test_mechanics.py`.
