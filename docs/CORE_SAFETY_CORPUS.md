# M1 Core Mechanics and Safety Corpus

Ticket #24 contributes the mechanics-correctness and catastrophic-safety half of the frozen M1 validation corpus defined by #10 and amended by #13.

## Corpus shape

The durable corpus lives in `tests/fixtures/ticket_24/` as canonical `FixtureEnvelope` JSON. It contains **33 promoted gated fixtures**:

- **23 CORE** mechanics/offense/coverage fixtures;
- **10 SAFETY_CRITICAL** catastrophic-risk fixtures;
- **0 CALIBRATION** fixtures.

Every fixture is replayed and evaluated through the generic #23 harness. The permanent corpus test pins the exact safety fixture set as well as the #10 taxonomy/severity summary, so ordinary offense examples cannot satisfy the safety quota merely by changing a severity label.

## Mechanics and taxonomy coverage

The CORE fixtures cover:

- ordinary Chop current AP/FAT cost consumption;
- ordinary attack HP/armor/kill effects;
- four kill-secure choices against Wait/End Turn as `obvious_offense_kill_secure` CORE cases rather than catastrophic-risk cases;
- a 3-AP affordability boundary where the brother still possesses Chop and the Hand Axe but the complete current affordance set excludes the 4-AP attack;
- a 95/100-fatigue affordability boundary where the same brother retains Chop and the Hand Axe but has only 5 fatigue headroom, so the complete current affordance set excludes the 10-FAT attack;
- a canonical range boundary where a visible hostile is more than one hex away and the complete current affordance set contains no melee attack;
- explicit ordinary-attack target actor, target kind, and affected-tile integrity;
- canonical `MOVE_TO` destination/path and resolved AP/FAT cost use;
- a known swamp destination whose current 4-AP/8-FAT movement cost is supplied by the resolved MOVE_TO affordance rather than re-derived by BB-Agent;
- elevation gain as an explicit positional consequence;
- clear and blocked known ranged line-of-sight exposure;
- Wait and End Turn deterministic turn-state effects;
- supported Recover, reload and equip commands;
- unknown special-skill coverage failure;
- impossible supplied AOO geometry coverage failure;
- multistep AOO movement without sufficient per-step resolved costs.

The SAFETY_CRITICAL fixtures are restricted to explicit catastrophic-risk cases:

- six disengagement/AOO traps, including lethal, high-probability, lower-probability-but-lethal, double-reaction and uphill cases;
- three direct-screen abandonment cases protecting allies at 10 HP, 5 HP, and 1 HP;
- one high-damage temptation where a 4-AP Chop consumes all remaining AP while the competing 2-AP MOVE_TO immediately protects a 10-HP ally and gains two elevation levels.

Together they contribute the ticket's required taxonomy families, including `core_legality_affordability`, `movement_path_zoc`, `obvious_offense_kill_secure`, `survival_catastrophic_risk`, `protection_formation`, `elevation_positioning`, `los_ranged_aoe`, `fatigue_resource_economy`, `tempo_wait_end_turn`, and `trace_failure_coverage`.

## Evidence and rules authority

These are handcrafted canonical fixtures, not claims of fresh live-game capture. Each fixture metadata record identifies:

- frozen contract basis `#10` and `#13`;
- `src/bb_agent/data/catalog.v1.json + manifest.v1.json` as the BB-Agent mechanics authority used by the evaluator;
- upstream Battle Brothers Scripts revision `162f498ac7c49b4c317bbf54718a595ecef6a65a` recorded by the catalog;
- a short per-fixture evidence note describing which resolved-current or modeled fact the assertion exercises.

The catalog records the reviewed upstream paths and source blobs for Chop, Recover, Reload Bolt and Hand Axe. Runtime state also carries the ruleset/content fingerprint used by trace/replay.

Per #13, this corpus does **not** reconstruct hypothetical Battle Brothers legality. A fixture's complete canonical `ActionAffordanceSet` is authoritative for the current executable commands. The AP, FAT, and range boundary fixtures therefore assert the contents of a complete supplied current affordance set; they do not add a second legality engine. Resolved current costs, paths and previews are consumed as supplied and are not re-derived or applied a second time.

No game-oracle annotation is smuggled into player-legal decision input. State-level helper annotations are stripped from this corpus. Later captured fixtures may add envelope-only oracle annotations for affordance completeness, but those remain diagnostic validation data.

## Affordability, range, targeting, and terrain boundaries

`t24-core-affordability-attack-excluded` keeps Chop possession and the Hand Axe in canonical state while the active brother has only 3 AP. The complete current affordance set contains only executable Wait, making the source-owned AP affordability boundary reviewable without independently reconstructing legality.

`t24-core-fatigue-affordability-attack-excluded` keeps the same skill and weapon while the active brother is at 95/100 fatigue. With only 5 fatigue headroom versus the known supplied current Chop fatigue cost of 10, the complete current affordance set again contains only executable Wait. This is the distinct FAT affordability boundary required by #24.

`t24-core-range-attack-excluded` places the visible hostile more than one canonical hex away and likewise asserts the complete supplied set contains no ordinary melee attack. `t24-core-target-affordance-integrity` complements it with the valid adjacent case, pinning the exact target actor, `ACTOR` target kind, and affected current tile supplied by the affordance.

`t24-core-terrain-resolved-move-cost` moves into known `swamp` terrain using a supplied executable path with resolved 4-AP/8-FAT costs. The terrain is canonical state context; the cost is source-resolved current-command data. M1 does not infer a parallel terrain movement-cost formula.

## AOO and catastrophic tail risk

The AOO fixtures provide contingent reactions as explicit current-command facts. They do not infer hidden reactions by probing hypothetical movement.

Every SAFETY_CRITICAL AOO case asserts both a positive movement/death-risk signal and a positive tail-risk penalty on the risky move. The lower-probability lethal case specifically protects against an evaluator that ignores catastrophic tails merely because the reaction hit chance is only 33%.

The risky `MOVE_TO` is explicitly forbidden as top recommendation, while the safe alternative is required to rank above it. This prevents a mean-damage-only implementation from satisfying the safety corpus.

## High-damage versus catastrophic flank

The current frozen M1 manifest does not contain a movement-coupled attack/charge family, so this corpus does not fabricate an action that both attacks and relocates the actor.

`t24-safety-high-damage-vs-protect-flank` instead makes the supported current-decision tradeoff genuinely exclusive. The active brother has exactly 4 AP. The ordinary Chop costs all 4 AP and produces more than 20 expected HP damage, leaving 0 AP after the action; the competing protective `MOVE_TO` costs 2 AP, creates the direct screen for a 10-HP ally, gains two elevation levels, and leaves 2 AP. The fixture requires the protective move to rank above the attack and forbids the damaging attack as top recommendation.

This does not claim that Chop itself moves the actor. It models the safety consequence that selecting the high-damage 4-AP action commits the remainder of the current turn away from the immediately available protective move. That stays within the frozen current-decision horizon and avoids inventing unsupported future legality.

## Explicit coverage failure

Three CORE fixtures intentionally expect `INCOMPLETE_COVERAGE`. They prove that a legal/current affordance with unsupported material mechanics is retained in the authoritative candidate set but prevents a complete recommendation.

Those traces must:

- keep the legal candidates visible;
- report `EVALUATION_UNSUPPORTED` diagnostics;
- contain no tactical selection;
- contain no evaluated candidate records that could masquerade as neutral/generic scores.

This is the #13 fail-closed behavior, not a tactical-quality disagreement.

## Information profile and scope

Most #24 fixtures use `omniscient_debug` deliberately to isolate exact mechanics and safety relationships without mixing in the uncertainty/no-cheat corpus owned by #25. The information profile is explicit in every fixture and remains part of state/trace identity.

#24 does not add live integration, network/LLM calls, keyboard/mouse execution, campaign logic, or a BB-Save-Toolkit tactical dependency. It is static offline validation data plus tests over the existing M1 kernel.
