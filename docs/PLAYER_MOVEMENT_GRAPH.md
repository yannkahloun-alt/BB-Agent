# Player Movement Graph and Reachability — Battle Brothers 1.5.2.3

Normative issue: **#98**. If this document and #98 conflict, #98 wins until the documentation is reconciled.

## Why this exists

Movement work is split into three different problems and must be solved in this order:

1. **Graph legality:** which movement transitions are possible from a landed tile.
2. **Resource reachability:** which destinations can be reached within AP/fatigue using legal transitions.
3. **Native path selection:** which legal route Battle Brothers' native navigator chooses when several routes exist.

Do not use uncertainty about (3) to guess or distort (1). Exact native path ranking/tie-breaking is deferred until the graph/reachable set is proven.

## Authority classes

- **SOURCE-PROVEN:** directly supported by installed 1.5.2.3 scripts / scripts revision `162f498ac7c49b4c317bbf54718a595ecef6a65a`.
- **PLAYER-BEHAVIOR:** established player-facing game behavior that production must reproduce even though the native navigator implementation is opaque.
- **NATIVE-DEFERRED:** native route-ranking behavior not required to define the movement graph.

## Phase A — transition topology

### Ordinary movement — SOURCE-PROVEN

A normal move is from the actor's current/landed tile to one canonical adjacent hex. A landing tile must exist in canonical topology, be traversable terrain, satisfy maximum elevation difference, and satisfy occupancy rules.

### Friendly-unit jump — PLAYER-BEHAVIOR + BOUNDED NATIVE OBSERVATION

A friendly-occupied adjacent tile is **not** a universal blocker.

- The player may pass/jump over exactly **one** allied unit to a legal landing tile beyond it.
- The allied tile is intermediate; it is not the landing/final destination.
- The actor must land before another ally jump.
- Two or more consecutive allied occupied tiles cannot be crossed as one transition.
- After landing, a later transition may jump one ally again.
- Enemies can never be jumped/passed through.
- The landing tile must itself be legal and unoccupied.
- Resource charging is the sum of the two constituent movement steps: landed tile → allied pass-over tile plus allied tile → landing tile. A bounded DEBUG_ORACLE sample from `tile:12:18` over `tile:12:19` to `tile:12:20` returned native `Tiles=2`, AP=4, FAT=6, exactly matching the two constituent steps and rejecting the direct-landing-only cost of AP=2, FAT=2.
- Production recomputes both constituent costs from player-legal topology and the owned actor's current movement tables. The DEBUG_ORACLE sample is validation evidence only and is never supplied as a production value.

### Enemy occupancy — PLAYER-BEHAVIOR

Enemy-occupied tiles are neither legal landings nor pass-through/jump tiles.

### Visible obstacles / occupied landing — SOURCE-COMPATIBLE / PLAYER-LEGAL

A currently visible occupied or non-traversable landing tile blocks the landing. For visible tiles, the player-facing source path permits the projection to derive a blocker from visibility-scoped `Tile.IsEmpty` without resolving hidden occupant identity. Actor relation then distinguishes ally pass-over from hostile blocking.

Remembered/non-visible occupancy remains unknown. Production must not inspect a hidden occupant to classify a remembered tile.

### Hidden units — PLAYER-BEHAVIOR / NO-CHEAT

Hidden units are ignored while constructing the player-known movement graph.

If real movement encounters a hidden occupied tile, movement stops before entering it and the unentered tile's movement cost is not deducted. Production enumeration must not inspect the hidden occupant before encounter.

## Phase B — transition costs and resource reachability

For ordinary landed-to-landed movement:

- terrain AP comes from `actor.getActionPointCosts()` using the landing tile terrain type;
- terrain fatigue comes from `actor.getFatigueCosts()`;
- current actor movement modifiers/perks/injuries are already represented by those actor tables and must not be reapplied independently;
- non-zero elevation adds `getLevelActionPointCost()` and `getLevelFatigueCost()`;
- climbing additionally adds `Const.Movement.LevelClimbingFatigueCost`;
- transitions exceeding `getMaxTraversibleLevels()` are illegal;
- `FatigueEffectMult` belongs to execution affordability after terrain/elevation fatigue is assembled;
- per successful executed step, AP and fatigue use the same rounding/update semantics as `actor.onMovementStep()`.

For a one-ally jump, apply the same ordinary step-cost rules independently to both constituent steps and sum them before testing affordability.

A destination is resource-reachable when **any** legal player-known route fits the actor's AP/fatigue resources. Production therefore maintains non-dominated AP/fatigue labels rather than choosing one route first and applying affordability afterward.

No invented non-negative `fatigueBudget` rule exists.

## Phase C — ZOC

- Entering hostile ZOC is allowed subject to normal movement legality.
- Player navigator settings include `ZoneOfControlCost = 4` and `AllowZoneOfControlPassing = true`.
- The +4 path cost applies when **leaving** ZOC, not when entering it.
- AOO/reaction evaluation is separate from graph legality and follows the actual route once one is resolved.

## Phase D — deferred native path selection

Do not solve these before Phase A/B/C reachable-set correctness:

- native A*/Dijkstra heuristic;
- priority queue ordering;
- equal-score tie-breaking;
- exact `resolved_path` identity among multiple legal routes;
- other `IsPlayer=true` native special cases unless a concrete reachability mismatch requires them.

These matter eventually for exact previews and AOO/ZOC geometry, but they are not prerequisites for proving the graph.

Bounded DEBUG_ORACLE validation may compare selected native paths/costs after Phase A/B/C is green, but native observations remain diagnostic-only and may not supply production values.

## TDD order

1. Write offline tests for Phase A/C transition topology.
2. Make simplified occupancy/ZOC code fail those tests.
3. Implement the minimum relation-aware transition generator to pass them.
4. Add transition-cost and Pareto resource-reachability tests.
5. Validate reachable destination sets offline.
6. Use bounded live/native smoke only for rules the source and frozen player behavior cannot decide.
7. Promote a resolved native-only rule into production only by expressing it from player-legal inputs and freezing the observation as regression evidence.

No production path-ranking/tie-break changes while Phase A/B/C tests are red.

## Current linked tickets

- #98 — normative specification; Phase A/B/C complete and closed
- #99 — ally-jump topology TDD cycle; closed
- #101 — minimal topology implementation after red tests
- #94 — broader movement fixture gate; closed
- #96 — occupancy semantics; closed
- #97 — ZOC exit semantics; closed
- #91 — responsive one-pass movement enumeration; live responsiveness remains to validate
- #92 — downstream bounded native-oracle validation
- #95 / #100 — documentation authority
- #87 — historical native-path reconstruction evidence
