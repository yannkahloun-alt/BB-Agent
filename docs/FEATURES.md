# M1 tactical feature contract

Issue #20 is the raw-feature layer between the canonical candidate outcome/transition models (#18, #19, #37, #40) and the later scoring policy in #21.

The feature extractor is intentionally **not a policy**. It emits deterministic physical facts, probability-backed expectations where probabilities are justified, and bounded envelopes where player-legal inputs are uncertain. It contains no weights, rankings, recommendation thresholds, or explanation policy.

## Public boundary

`extract_candidate_features(authority, state, action_reference)` first resolves the action through the #40 canonical candidate boundary. A caller-supplied `ActionAffordance` is therefore only an identity reference; its costs, preview, target, path, or reaction data are never trusted over the normalized `TacticalState` copy.

The extractor then reuses the already-supported current-command model:

- ordinary single-target attacks use #18 `AttackOutcome`;
- movement, contingent AOO, Wait, End Turn, Recover, reload, and supported equipment actions use #19/#37 `TransitionOutcome`;
- unsupported or insufficiently represented candidates preserve `INCOMPLETE_COVERAGE` / `EVALUATION_UNSUPPORTED`;
- stale/invalid canonical input preserves `VALIDATION_FAILURE`.

No second player command or enemy turn is simulated.

## `MetricRange`

Every feature that can vary is represented as:

```text
minimum
maximum
expected?   # only when a justified probability model covers the represented domain
```

For exact facts all three values are the same. For unweighted `SET`, `RANGE`, or otherwise bounded epistemic alternatives, only `minimum`/`maximum` are authoritative and `expected` is absent. The extractor never substitutes a midpoint for unknown enemy information.

Immediate attack/AOO RNG may provide a real expectation because #18 supplies a probability distribution. Epistemic attack scenarios remain an envelope of RNG expectations unless their belief weights are actually justified.

## Semantic ownership

These families are deliberately separated so #21 does not need hidden subtraction rules to avoid accidental double-counting.

| Family | Owns | Explicitly does not own |
|---|---|---|
| `enemy_effect` | Direct hostile HP/armor effect and kill probability from the current command | Posture/threat credit for removing that same target |
| `friendly_harm` | Immediate self/ally harm and current-move interruption/AOO consequences | Future hostile pressure or formation geometry |
| `threat` | Post-action hostile contact, bounded ZOC pressure, and LOS-exposure proxies | Immediate AOO damage; inferred enemy commands; enemy attack probabilities |
| `position` | Elevation level/change and elevation relationship at contact | Damage, formation, or control value |
| `formation` | Friendly adjacency and direct one-hex screen geometry | Pathfinding, strategic unit value, or hostile damage probability |
| `control` | The active actor's geometric contribution to an ally-supported flank/surround | Incoming contact pressure already owned by `threat` |
| `mobility` | Open-adjacent-tile geometry and current `MOVE_TO` completion probability | Future `MOVE_TO` legality, repathing, or second-command search |
| `resources` | Remaining AP/FAT/headroom and explicit resolved command resource costs | A policy claim that spending AP/FAT/ammo is intrinsically bad |
| `future_capacity` | Residual AP/FAT affordability against deduplicated **current-command cost templates** | A claim that any template remains legal after the action |
| `tempo` | Known Wait/end-turn/current turn-state facts | Initiative prediction or future enemy response simulation |

The same table is emitted with every `TacticalFeatures` value as structured `semantic_ownership` metadata.

## Threat, ZOC, and LOS boundaries

### Adjacent hostile pressure

This is geometry: the number/range of living hostile positions adjacent to the resulting actor tile. Exact hostile positions produce exact counts. Sets/distributions without an authoritative probability become a range. Unknown positions conservatively widen the possible count.

### Hostile ZOC pressure

Adjacency is **not** promoted to AOO capability. #37 explicitly forbids inventing an AOO solely from adjacency, and the canonical state currently has no general hostile-ZOC-capability field. Therefore:

```text
hostile_zoc_pressure.minimum = 0
hostile_zoc_pressure.maximum = adjacent_hostile_pressure.maximum
```

A current movement's supplied contingent AOOs remain immediate consequences in `friendly_harm`; they are not generalized into a future enemy-action model.

### Ranged/LOS exposure

`ranged_los_exposure` is a bounded **LOS exposure candidate** count, not proof that a hostile has a legal ranged attack. It uses only canonical axial coordinates and each intermediate tile's `blocks_line_of_sight` knowledge. Known blockers close the corridor, known-clear intermediates open it, and uncertain blockers preserve a range.

The feature deliberately does not infer weapon range, hidden ranged skills, attack legality, hit chance, or future enemy intent.

## Formation and blocking proxy

The frozen state does not provide a complete tactical path-blocking oracle. The #20 formation proxy therefore uses one narrow, inspectable geometry:

- the active actor is adjacent to a friendly unit;
- the actor is adjacent to a hostile;
- friendly and hostile lie on opposite sides of the actor on the same axial line.

That triple is a `direct_screen_link`. For a `MOVE_TO`, the extractor reports created/lost link counts and the affected friendly actor IDs. This makes a classic "vacate the blocking tile and expose the backliner" fact visible without claiming the hostile has a particular future move or searching a route.

No HP threshold is embedded. A vulnerable ally's HP remains a separate canonical fact for #21/trace policy to consume later.

## Mobility and future capacity are not future legality

`open_adjacent_reposition_tiles` uses current map occupancy plus known/possible `traversable` and `blocking` values. It is a local geometric flexibility proxy only.

`future_capacity` deduplicates the current `ActionAffordanceSet` into AP/FAT cost templates and asks which templates would fit the actor's residual AP/FAT headroom. This is intentionally weaker than a follow-up action set:

- no target is selected;
- no command is committed;
- no post-action `isUsableOn` or path legality is synthesized;
- no template is claimed to remain executable after the current command.

This preserves the #13 boundary while still exposing fatigue/AP lockout information for #21.

## Immediate outcome vs posture

Immediate friendly damage/death/interruption is owned by `friendly_harm`. Posture/resource/future-capacity metrics use surviving immediate transition branches; a lethal AOO is not silently converted into a destination posture. `movement_completion_probability` separately reports whether the supplied move actually completes, including the #37 rule that any AOO hit interrupts the attempted step.

For ordinary attacks, posture/threat features intentionally keep the pre-command hostile set rather than crediting target removal a second time; target removal probability belongs to `enemy_effect.kill_probability`.

## Non-goals

This layer does not add:

- #21 scores, weights, ranking, tie-breaking, or explanation policy;
- full enemy-response trees;
- hypothetical future player legality;
- inferred AOOs from adjacency;
- hidden enemy stats/capabilities;
- new Battle Brothers mechanics families merely to improve feature richness;
- live-game acquisition or execution.

If a later gated safety case truly requires a future enemy action tree instead of these bounded current-state/post-command proxies, the #20/#12 escalation rule applies rather than extending this module into search.
