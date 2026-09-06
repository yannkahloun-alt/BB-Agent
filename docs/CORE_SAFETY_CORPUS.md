# M1 Core Mechanics and Safety Corpus

Ticket #24 contributes the mechanics-correctness and catastrophic-safety half of the frozen M1 validation corpus defined by #10 and amended by #13.

## Corpus shape

The durable corpus lives in `tests/fixtures/ticket_24/` as canonical `FixtureEnvelope` JSON. It contains **25 promoted gated fixtures**:

- **14 CORE** mechanics/coverage fixtures;
- **11 SAFETY_CRITICAL** tactical-safety fixtures;
- **0 CALIBRATION** fixtures.

Every fixture is replayed and evaluated through the generic #23 harness. The permanent corpus test also checks the #10 taxonomy/severity summary rather than relying on fixture count alone.

## Mechanics and taxonomy coverage

The CORE fixtures cover:

- ordinary chop current AP/FAT cost consumption;
- ordinary attack HP/armor outcome effects;
- canonical `MOVE_TO` destination/path and resolved AP/FAT cost use;
- elevation gain as an explicit positional consequence;
- clear and blocked known ranged line-of-sight exposure;
- Wait and End Turn deterministic turn-state effects;
- supported Recover, reload and equip commands;
- unknown special-skill coverage failure;
- impossible supplied AOO geometry coverage failure;
- multistep AOO movement without sufficient per-step resolved costs.

The SAFETY_CRITICAL fixtures cover:

- four kill-secure positions against Wait/End Turn alternatives;
- five disengagement/AOO traps, including lethal, high-probability, double-reaction and uphill cases;
- vacating a direct screen protecting a 10-HP ally;
- choosing immediate flank protection over a materially damaging ordinary attack.

Together they contribute the ticket's required taxonomy families, including `core_legality_affordability`, `movement_path_zoc`, `obvious_offense_kill_secure`, `survival_catastrophic_risk`, `protection_formation`, `elevation_positioning`, `los_ranged_aoe`, `fatigue_resource_economy`, `tempo_wait_end_turn`, and `trace_failure_coverage`.

## Evidence and rules authority

These are handcrafted canonical fixtures, not claims of fresh live-game capture. Each fixture metadata record identifies:

- frozen contract basis `#10` and `#13`;
- `src/bb_agent/data/catalog.v1.json + manifest.v1.json` as the BB-Agent mechanics authority used by the evaluator;
- upstream Battle Brothers Scripts revision `162f498ac7c49b4c317bbf54718a595ecef6a65a` recorded by the catalog;
- a short per-fixture evidence note describing which resolved-current or modeled fact the assertion exercises.

The catalog itself records the reviewed upstream paths and source blobs for Chop, Recover, Reload Bolt and Hand Axe. Runtime state also carries the ruleset/content fingerprint used by trace/replay.

Per #13, this corpus does **not** reconstruct hypothetical Battle Brothers legality. A fixture's complete canonical `ActionAffordanceSet` is authoritative for the current executable commands. Resolved current costs, paths and previews are consumed as supplied; they are not re-derived and applied a second time.

No game-oracle annotation is smuggled into player-legal decision input. Later captured fixtures may add envelope-only oracle annotations for affordance completeness, but those remain diagnostic validation data.

## AOO and catastrophic tail risk

The AOO fixtures provide contingent reactions as explicit current-command facts. They do not infer hidden reactions by probing hypothetical movement.

Every SAFETY_CRITICAL AOO case asserts both:

- a positive movement-interruption probability; and
- a larger tail-risk penalty on the risky move than on the safe alternative.

The risky `MOVE_TO` is explicitly forbidden as top recommendation, while the safe alternative is required to rank above it. This prevents a mean-damage-only implementation from satisfying the safety corpus.

## High-damage versus catastrophic flank

The current frozen M1 manifest does not contain a movement-coupled attack/charge family. This corpus therefore does not fabricate an action that both attacks and relocates the actor.

`t24-safety-high-damage-vs-protect-flank` encodes the representable **current-decision safety tradeoff** instead: from an exposed flank, the actor can either take an ordinary Chop with more than 20 expected HP damage or immediately `MOVE_TO` the screen protecting a 10-HP ally. The protective move also gains two elevation levels. The fixture requires the screen move to rank above the attack and forbids the damaging attack as top recommendation.

This distinction is deliberate: the attack does not secretly move or create a synthetic future state. A literal attack-that-moves-and-opens-a-flank fixture should only be added after such a mechanic family is explicitly supported by the manifest. Until then, the M1-safe assertion is the opportunity cost between damage-now and protection-now in the authoritative current affordance set.

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
