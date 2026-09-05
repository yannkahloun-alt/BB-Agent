# M1 implementation status

This document is the durable handoff for BB-Agent's M1 offline tactical decision-kernel work. It records durable implementation state and contract amendments. GitHub issues remain authoritative for detailed acceptance criteria and live work status.

## Current phase

BB-Agent is in the M1 offline tactical decision-kernel implementation phase.

M1 consumes a canonical tactical state plus a complete current `ActionAffordanceSet`, evaluates only explicitly supported mechanics, later ranks them with risk-sensitive logic, and emits deterministic/replayable traces. Live game capture, execution automation, generalized future-state legality/search, campaign automation, and ML remain outside M1.

## Implemented through #20

Completed implementation/hardening tickets:

- #14 — project, test, CI, deterministic serialization/hash and version skeleton.
- #15 — canonical tactical state and `ActionAffordance` contracts.
- #16 — fixture loading, validation and replay input envelope.
- #17 — mechanics coverage manifest and immutable local rules/content catalog substrate.
- #18 — ordinary single-target attack outcome model.
- #19 — `MOVE_TO`, contingent AOO representation, and simple deterministic action transitions.
- #37 — source-faithful disengagement/AOO movement semantics and transition fixtures.
- #40 — canonical candidate resolution, reaction attack context, resolution ownership, failure-class and identity hardening.
- #20 — raw tactical positioning, threat, formation, resource, tempo, and future-capacity feature extraction.

### #18 supported outcome boundary

The packaged ordinary-attack model is deliberately narrow. The current production baseline supports the vanilla hand-axe / Chop family declared in the mechanics manifest.

The model:

- consumes resolved player-visible hit chance without reconstructing hidden enemy defense;
- keeps preview-resolved values authoritative for the stages they already represent;
- models independent regular-damage and armor-damage rolls from the pinned Battle Brothers scripts;
- applies the pinned armor/direct-damage ordering and final HP rounding;
- models the standard head/body split and Chop's head damage multiplier at the correct damage stage;
- exposes immediate actor/target resource outcomes and kill probability;
- separates aleatory combat RNG from epistemic uncertainty;
- represents `SET`/`RANGE` player-legal uncertainty as an unweighted robustness domain unless a justified probability distribution exists;
- keeps omniscient-debug truth separate from player-legal inputs;
- fails unsupported perks, effects, equipment, variants or missing target knowledge visibly rather than approximating them.

PR #33 merged the corrected #18 implementation into `main`; issue #18 is closed.

## #19 / #13 contingent-reaction amendment

Implementation of #19 exposed a real gap in the frozen #13 contract: a current `MOVE_TO` command can trigger a hostile attack of opportunity, while the original canonical state contained only the active actor's executable commands and no production-safe representation of the contingent enemy reaction.

#19 added the smallest canonical contingent-reaction representation necessary for movement AOOs. A post-freeze amendment to #13 records the same exception. All other #13 boundaries remain frozen.

The contingent reaction context may carry, as applicable:

- the movement path step / trigger point;
- reacting actor identity;
- reaction kind (`AOO` for the current implementation);
- reaction skill/content identity or an explicitly unsupported mechanic identity;
- player-legal knowledge/provenance needed by the reaction outcome model;
- legitimate resolved reaction inputs where the player can know them;
- omniscient-debug/oracle truth separately.

The representation is **not** a second enemy `ActionAffordanceSet` and is **not** a generalized enemy-turn action model.

### No-cheat / uncertainty requirements

- Do not synthesize exact enemy MAtk/MDef, hidden perks/resources, or exact reaction odds from omniscient runtime state in `player_legal`.
- `omniscient_debug` may carry exact truth separately for paired diagnostics.
- Unsupported reaction skills/equipment/effects or insufficient player-legal knowledge make the movement candidate coverage-incomplete rather than being dropped or approximated.

## Post-#19 movement hardening — #37

Issue #37 hardens the merged #19 transition model before positioning/exposure features consume its results.

The supported boundary is:

- contingent reactions come from the fixture/future adapter; BB-Agent does not infer enemy AOO capability merely from adjacency;
- for a supported single-step disengagement, the resolved movement cost belongs to the attempted step;
- all supplied AOOs for that movement attempt may resolve;
- only the all-miss branch reaches the destination;
- any hit, lethal or nonlethal, interrupts the step and leaves the mover on the pre-step tile;
- death may suppress later reactions because the mover is no longer a living target;
- multi-step movement with contingent reactions is coverage-incomplete while the canonical contract contains only aggregate path cost and cannot represent an early interruption's partial AP/FAT cost without guessing;
- transition regression fixtures use action-specific movement/Wait/Recover/reload costs and coherent map states;
- reload fixtures include the item-bound executable `reload_bolt` context, a mainhand crossbow and nonempty bolt ammunition. The current canonical `ItemState` does not encode a loaded/unloaded flag, so the complete executable reload affordance is authoritative for current usability while transition effects record `loaded` and `ammo_consumed` consequences.

## Pre-#20 evaluation hardening — #40

#40 closes the remaining seam between canonical current commands, structural mechanics coverage and concrete outcome/transition evaluation.

The hardened boundary is:

- current-candidate evaluators resolve the canonical action from normalized `TacticalState` plus `action_id`; a legacy caller may still pass an `ActionAffordance` reference, but only its `action_id` is consumed and divergent AP/FAT/preview/action fields are ignored;
- manifest/family support remains structural coverage, while concrete supported-family gaps such as unsupported effects, equipment or insufficient knowledge remain per-candidate `EVALUATION_UNSUPPORTED`; evaluator-facing structural failures are distinguished with `MECHANICS_UNSUPPORTED`;
- invalid/stale state, ruleset or candidate identity remains `VALIDATION_FAILURE` rather than being relabelled as incomplete coverage;
- outcome/transition code catches only deliberate evaluation boundary errors; unexpected programmer exceptions are allowed to surface;
- canonical AP/FAT and displayed-hit-chance consumption now passes through the #17 `ResolutionLedger` ownership checks, and returned outcomes retain the resulting ledgers for later trace provenance;
- contingent AOOs no longer synthesize enemy `ActionAffordance` commands. A small internal attack-evaluation context lets canonical player attacks and supplied AOOs use the same ordinary-attack content/effect/damage primitive;
- contingent-reaction consequence data is not part of the player's command identity. Equivalent commands keep the same `action_id` across acquisition provenance and reaction-knowledge changes, while the reaction facts remain in semantic state identity and therefore still change replay/evaluation identity;
- the canonical tactical-state/action-affordance contract identifiers carry the explicit `identity-40` amendment.

## #20 tactical feature boundary

#20 consumes only canonical candidate outcomes/transitions at or beyond the #40 boundary and exposes raw, inspectable feature families for later #21 scoring.

The feature layer:

- keeps direct enemy effect separate from posture/threat so target removal is not silently credited twice;
- keeps immediate AOO/self-harm and interruption consequences separate from future hostile-pressure proxies;
- exposes adjacent-hostile pressure exactly or as a bounded range from canonical position knowledge;
- treats hostile ZOC capability conservatively because adjacency alone is not proof of AOO capability;
- exposes ranged/LOS corridor exposure without inventing enemy ranged legality, hit chance, or intent;
- reports elevation, friendly adjacency, direct-screen creation/loss, flank/surround contribution, and local reposition-space facts;
- reports residual AP/FAT/headroom and explicit ammo/charge/item costs;
- computes residual AP/FAT affordability only against deduplicated current-command cost templates and does not claim those commands remain legal after the candidate;
- reports current Wait/end-turn facts without initiative prediction or enemy-response search;
- preserves uncertainty as ranges when player-legal inputs do not justify a probability distribution;
- documents semantic ownership for every feature family in `docs/FEATURES.md` and in the structured feature result.

#20 does not add #21 weights/ranking/explanation policy, generalized enemy actions, future-turn search, inferred AOOs, or broader mechanics coverage.

## Frozen M1 invariants

1. Current executable commands come from `ActionAffordanceSet`; BB-Agent does not clone arbitrary Battle Brothers current-action legality/pathfinding.
2. `player_legal` and `omniscient_debug` are explicit information profiles.
3. Debug omniscience is diagnostic only and cannot silently influence production decisions.
4. Unknown information remains unknown; hidden exact values are not substituted for convenience.
5. Unsupported mechanics fail visibly with structured incomplete coverage.
6. Preview-resolved/current values are applied once; later stages must not double-apply modifiers already represented in them.
7. Decision behavior must remain deterministic and replayable from canonical inputs/configuration.
8. Risk and uncertainty remain inspectable rather than collapsed into an opaque score.
9. No network or LLM belongs in the tactical decision loop.
10. BB-Save-Toolkit is not a tactical runtime dependency for M1.
11. M1 is an offline decision kernel; live capture/execution is post-M1.
12. Tests validate contracts; they do not redefine frozen semantics.

## Remaining M1 sequence

After #20 lands on `main`:

- #21 — risk-sensitive evaluator, deterministic selection and explanation facts.
- #22 — decision trace, deterministic replay and performance diagnostics.
- #23 — validation harness and fixture expectation semantics.
- #24 — core mechanics and safety-critical fixture corpus.
- #25 — tactical-quality, uncertainty and no-cheat fixture corpus.
- #26 — evaluator calibration against the gated corpus.
- #27 — final M1 offline tactical decision-kernel validation/closure gate.

Do not skip directly into live adapter/shadow execution work before #27 closes M1.

## Fresh-agent startup

A fresh implementation/review agent should begin with:

1. root `AGENTS.md`;
2. this `docs/M1_STATUS.md`;
3. the current GitHub ticket and every frozen spec/dependency it references;
4. the relevant implementation/tests on `main`.

Repository/worktree ownership must be inspected before destructive cleanup. Preserve unrelated or inaccessible local artifacts rather than forcing removal.
