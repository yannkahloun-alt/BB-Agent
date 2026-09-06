# M1 closure report

## Verdict

**M1 CLOSED.**

Ticket #27 validates the frozen offline tactical decision kernel after completion of implementation tickets #14–#26. The decision-kernel revision validated by the closure audit is `a4c213e0bf1b2f6ab3a20a8a1fe8eb675ad7a03f`, the squash merge of #26. The #27 closure change itself adds only validation/reporting/benchmark tooling and project-status documentation; it does not change tactical ranking semantics.

M1 remains an **offline current-decision kernel**. This verdict does not authorize live game capture, advisor UX, command execution, autonomous combat, or campaign automation. Those belong to the post-M1 specification/research phase required by #27 and frozen #10 promotion policy.

## Frozen identities

| Item | Final M1 value |
| --- | --- |
| M1 spec | `issues-1-through-13.freeze-1` |
| Information policy | `issue-2.amended-by-13` |
| Tactical state | `issue-3.amended-by-13.contingent-reactions-19.identity-40` |
| Action affordance | `issue-4.amended-by-13.contingent-reactions-19.identity-40` |
| Evaluation contract | `issue-5.amended-by-13` |
| Uncertainty contract | `issue-6.amended-by-13` |
| Decision trace contract | `issue-7.amended-by-13` |
| Fixture schema | `bb-agent-fixture.v1` |
| Validation harness | `m1-validation-harness.v1` |
| Trace schema | `bb-agent-decision-trace.v1` |
| Evaluator model | `risk-evaluator.v1` |
| Evaluation config | `m1-evaluation-profile.v2` |
| Evaluation profile fingerprint | `2e0ff58c4c57a80dc37eb86da5d49ef573057abd73eb158801f5c600c0c6ffcb` |
| UnitValuePolicy | `m1-common-preservation.v1` |
| UnitValuePolicy fingerprint | `170f540b3f76cb01ca88048dcb13cb66f57f96b2ea464c6a122292309179c2b7` |
| Mechanics manifest | `bb-agent-mechanics-manifest.v1` |
| Mechanics manifest fingerprint | `9f692baf73145ead5be654c5044c16cf70c8d5d7dad83ece9525bae252bb67e8` |
| Catalog | `bb-agent-catalog.v1` |
| Ruleset/content fingerprint | `4c4b714832d1989740a6f07dce058c11aa1e9123056966ede06ce42d1df182bd` |
| Pinned Battle Brothers scripts revision | `162f498ac7c49b4c317bbf54718a595ecef6a65a` |
| Declared outcome model | `ordinary-attack.v1` |
| Observed outcome/transition models | `ordinary-attack.v1`, `transitions.v1` |
| Shared workflow pin | `ff0647d3dc205a47734d569ae5247ee4ba9109e9` |

## Gated fixture corpus

The complete #24 + #25 corpus was loaded from static local fixture files and run through the generic #23 harness twice.

- total fixtures: **54**;
- promoted gated fixtures: **54**;
- calibration-only fixtures: **0**;
- safety-critical fixtures: **10**;
- uncertainty/no-cheat fixtures: **11**;
- blocking failures: **0**;
- review findings: **0**;
- repeated semantic results: **identical** across both runs, including output fingerprints, statuses, chosen actions and rankings.

Severity counts:

- `CORE`: 24;
- `QUALITY`: 20;
- `SAFETY_CRITICAL`: 10.

Information-profile counts:

- `player_legal`: 14;
- `omniscient_debug`: 40.

Every required #10 taxonomy family is represented:

| Taxonomy | Count |
| --- | ---: |
| `core_legality_affordability` | 11 |
| `movement_path_zoc` | 17 |
| `los_ranged_aoe` | 4 |
| `obvious_offense_kill_secure` | 13 |
| `survival_catastrophic_risk` | 14 |
| `protection_formation` | 6 |
| `elevation_positioning` | 9 |
| `fatigue_resource_economy` | 6 |
| `tempo_wait_end_turn` | 5 |
| `control_disable_threat_priority` | 6 |
| `uncertainty_no_cheat` | 11 |
| `trace_failure_coverage` | 4 |

## Coverage health

No supported ranking fixture ends in `INCOMPLETE_COVERAGE`.

Exactly four dedicated CORE coverage-health fixtures intentionally return `INCOMPLETE_COVERAGE`, all with explicit `expected_status: INCOMPLETE_COVERAGE`, no ranking assertions and structured `EVALUATION_UNSUPPORTED` diagnostics:

1. `t24-core-coverage-impossible-aoo-geometry`;
2. `t24-core-coverage-multistep-aoo-costs`;
3. `t24-core-coverage-unknown-special`;
4. `t25-no-cheat-coverage-failure-health`.

This is the required fail-closed behavior, not a hidden accuracy failure.

## Mechanics manifest summary

Supported M1 families:

- `ordinary_attack` — `ordinary-attack.v1`;
- `move` — `transitions.v1`, requiring supported `aoo` handling where supplied;
- `aoo` — `transitions.v1`;
- `wait` — `transitions.v1`;
- `end_turn` — `transitions.v1`;
- `equip` — `transitions.v1`;
- `recover` — `transitions.v1`;
- `reload` — `transitions.v1`.

`special` remains explicitly `EVALUATION_UNSUPPORTED`: additional control, AOE, defensive and special mechanics require separately tested declarations. M1 does not guess a generic score for them.

## Replay and determinism

Two complete 54-fixture harness runs on the same canonical inputs produced identical semantic result tuples for every fixture:

- output fingerprint;
- decision status;
- chosen action;
- complete ranking.

The normal fixture harness also performs exact decision replay and makes replay mismatch a hard assertion. The final corpus has zero replay failures.

No deterministic sampling is currently required by the promoted corpus: the reference benchmark observed a maximum `sample_count` of **0**. Exact/analytic enumeration remains deterministic; the maximum exact branch count observed during the benchmark was **4,105**.

## No-cheat / information separation

All 14 `player_legal` fixtures were recursively inspected after canonical serialization. The closure scan found:

- **0** `DEBUG_GROUND_TRUTH` knowledge values;
- **0** `DEBUG_ORACLE` resolution authorities;
- **0** non-null action `debug_ground_truth` payloads.

Paired player-legal/omniscient fixtures and hidden-state belief fixtures remain part of the promoted corpus, and their semantic assertions pass.

## UnitValuePolicy boundary

The #25 identical-state pair was re-evaluated during closure:

- both fixtures contain the same canonical `TacticalState` and state ID;
- default policy unit value: **1.0**;
- explicit high-value policy unit value: **4.0**;
- movement tail-risk selection penalty: approximately **2.125 -> 8.5**;
- policy fingerprints differ while state identity is unchanged;
- both fixture validations pass.

The production package declares no runtime dependencies, and the M1 `src/` tree contains no BB-Save-Toolkit import/dependency token. Strategic unit value remains explicit evaluation context rather than a synchronous toolkit dependency.

## Reference-machine latency benchmark

The reproducible benchmark command is `python tools/benchmark_m1.py`. It times `run_decision_trace()` directly after loading fixtures/mechanics and warming the process; fixture loading is outside the measured decision window.

Reference run provenance:

| Field | Value |
| --- | --- |
| Decision-kernel revision | `a4c213e0bf1b2f6ab3a20a8a1fe8eb675ad7a03f` |
| Git tree | `fa7238fdeb39fc36243fe54b8879e506c0f1345f` |
| CPU | AMD EPYC 9V74 80-Core Processor |
| Exposed logical CPUs | 5 |
| Virtualization | KVM |
| OS/kernel | Linux 6.18.35 x86_64, glibc 2.41 |
| Python | CPython 3.12.14 |
| Python acquisition | `actions/setup-python` 3.12 runtime exported as an artifact, then executed locally |
| Network during benchmark | unavailable / not used |
| Fixture set | 54 promoted #24/#25 fixtures |
| Warm state | one complete 54-fixture decision pass before measurement |
| Measured passes | 7 |
| Measured decisions | 378 |
| Evaluation profile | `m1-evaluation-profile.v2` / fingerprint above |
| Mechanics manifest | `bb-agent-mechanics-manifest.v1` / fingerprint above |
| Sampling | 0 samples; exact/analytic models only |

Measured whole-decision wall clock:

- median: **55.77 ms** — target <= 250 ms;
- p95: **95.15 ms** — target <= 1,000 ms;
- maximum: **158.58 ms** — hard ceiling <= 3,000 ms.

Measured evaluator-stage totals:

- median: **43.04 ms**;
- p95: **78.76 ms**;
- maximum: **112.42 ms**.

The slowest measured whole decision was `t25-no-cheat-flip-debug-high` at about **158.58 ms**. Its recorded evaluator stages were dominated by `outcome_and_features` (~81.16 ms), with validation (~7.48 ms), coverage (~2.80 ms), scoring (~0.81 ms) and selection (~0.07 ms) much smaller. No suspicious performance stage or budget overage remains.

The benchmark passes all frozen #10 engineering targets with substantial margin.

## Warnings and diagnostics reviewed

- blocking fixture failures: 0;
- non-blocking review/calibration findings: 0;
- unexpected coverage failures: 0;
- ranking fixtures with incomplete coverage: 0;
- player-legal debug leakage: 0;
- deterministic sampling calls: 0;
- intentional coverage failures: the four named fixtures above, each with `EVALUATION_UNSUPPORTED`;
- performance overages: 0.

## Accepted M1 limitations

The following are accepted frozen limitations, not closure blockers:

- mechanics coverage is manifest-driven and intentionally incomplete;
- general `special` skills/control/AOE/defensive families remain unsupported unless separately declared and tested;
- M1 evaluates one current atomic command plus bounded post-action/exposure proxies, not a deep future-state search tree;
- the real Battle Brothers future RNG stream is not reproduced;
- full online opponent-belief learning is deferred;
- current executable commands are supplied by a complete `ActionAffordanceSet`; M1 does not reconstruct arbitrary Battle Brothers current-command legality;
- no live game adapter, shadow/advisor UX, command execution, autonomous combat, retreat policy or campaign agent is included;
- the tactical loop has no network, LLM or BB-Save-Toolkit runtime dependency.

## Calibration-only disagreements

**None.** The final promoted corpus contains zero calibration-only fixtures and the closure harness reports zero review findings.

## Post-M1 next step

The next work is a new specification/research phase for live Battle Brothers state plus `ActionAffordanceSet` capture and shadow/advisor operation. It must preserve the frozen no-cheat boundary and use the #10 promotion gates. Supervised execution remains gated on later real-battle shadow evidence and is not authorized by M1 closure.
