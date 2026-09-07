# Player-Legal Movement Authority

GitHub issue #98 is the normative post-M1 contract for player movement graph and reachability. This document mirrors that boundary; it does not add mechanics beyond #98.

## Three separate questions

Movement work must keep these questions distinct:

1. **Graph legality**: which transitions exist in the player-known tactical topology.
2. **Resource reachability**: whether at least one legal player-known route can be executed with the actor's current AP and fatigue resources.
3. **Native path selection**: which legal route Battle Brothers' native navigator chooses when multiple routes are possible.

Production must solve (1) and (2) without requiring (3). Exact native heuristic, route preference, and tie-breaking remain deferred until reachable-set correctness is established.

## Production information boundary

Production movement is `player_legal`. It derives graph legality and reachability from player-known topology, currently visible observations, remembered terrain where permitted, and movement data belonging to the active player actor.

Hidden current occupancy must not be consulted while enumerating the player-known graph. If actual movement later encounters a hidden occupied tile, Battle Brothers stops the move before entering that tile and does not charge movement cost for the unentered tile. DEBUG_ORACLE may observe hidden/native truth for validation, but it must never supply production values.

Visible actor occupancy is relation-aware. A visible allied unit is not a universal blocker: the player may pass over exactly one ally to a legal landing tile beyond it. The allied tile is intermediate only. The actor must land before another allied jump can occur. Enemies cannot be jumped or crossed. Visible occupied landing tiles and visible non-traversable tactical objects block their landing tile.

Visible non-actor blocker acquisition is still unresolved. The forensic snapshot showed visible scenery occupiers, but their tile terrain and property fields were indistinguishable from ordinary empty tiles; the differentiating data was the raw occupant/entity state. A production blocker bit therefore must not be inferred from raw `Tile.IsEmpty`, `getEntity()`, or hidden-actor state merely to distinguish scenery, because doing so would inspect hidden occupancy before encounter. Until a source-proven player-facing blocker signal is identified, production keeps this limitation explicit instead of violating the no-cheat boundary.

## Source-derived movement costs

For ordinary resource-resolved steps, production uses the active actor's current modified movement tables:

- `actor.getActionPointCosts()` for terrain AP cost;
- `actor.getFatigueCosts()` for terrain fatigue cost;
- `actor.getLevelActionPointCost()` for non-zero elevation difference;
- `actor.getLevelFatigueCost()` for non-zero elevation difference;
- `Const.Movement.LevelClimbingFatigueCost` additionally when climbing;
- `actor.getMaxTraversibleLevels()` to reject excessive elevation differences.

The actor movement tables already incorporate actor-specific movement modifiers such as Pathfinder. Those modifiers must not be applied a second time.

`FatigueEffectMult` belongs to execution affordability after terrain/elevation fatigue is assembled. Each executed step must fit current AP and fatigue capacity, and AP/fatigue are rounded after each successful step according to the source-derived movement execution semantics.

A destination is resource-reachable when **any** legal player-known route reaches it within those resources. Production therefore preserves non-dominated AP/fatigue states instead of selecting one route first and then rejecting the destination if only that route is unaffordable.

## Zone of control

Entering hostile ZOC is legal subject to ordinary movement legality. The player navigator's `ZoneOfControlCost = 4` penalty applies to the transition **leaving** hostile ZOC, not to the transition entering it. `AllowZoneOfControlPassing = true` is part of the source configuration.

AOO/reaction handling belongs to the actual resolved/executed path. It must not be used to infer hidden occupancy or to force native route preference during graph/reachability construction.

## DEBUG_ORACLE

DEBUG_ORACLE is separate, opt-in, bounded, and validation-only. It may call native pathfinding for a narrowly defined unresolved rule after offline graph/reachability tests are green, but those observations must never become direct production inputs.

The currently unresolved ally-jump AP/fatigue charging convention is intentionally isolated behind a one-sample DEBUG_ORACLE probe. Until that rule is established, allied jump topology may be represented while its resource cost remains unresolved in production.

## Performance invariant

Production must never restore the old per-destination native `findPath()` loop. That implementation made an ordinary 9 AP turn issue roughly 60 synchronous native pathfinding calls and froze tactical play. Reachability must be computed with a bounded local search over player-known topology and owned-actor movement data.

## Test authority

Issue #94 is the deterministic offline fixture gate for #98. The executable corpus covers terrain, elevation, actor-modified costs, AP/fatigue limits, relation-aware actor occupancy, allied jump topology, a synthetic known-blocker class, hidden-state exclusion, ZOC entry/exit placement, rooted/stunned movement, deterministic adjacency, and any-feasible-route resource reachability.

The synthetic blocker fixture proves graph behavior once a legal blocker observation exists; it does not claim that production has already acquired visible non-actor blockers safely. Native chosen-path identity and tie-breaking are not prerequisites for this corpus.
