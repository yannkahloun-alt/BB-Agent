"""Deterministic offline model for the frozen player-known movement rules in #98.

This module is deliberately independent of Battle Brothers' native navigator. It
models graph legality and resource reachability only; exact native route choice
is outside its contract.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import floor


@dataclass(frozen=True)
class Tile:
    tile_id: str
    terrain: int
    level: int
    neighbors: tuple[str | None, ...]


@dataclass(frozen=True)
class ActorMovement:
    ap: int
    fatigue: int
    fatigue_max: int
    ap_costs: Sequence[int | float]
    fatigue_costs: Sequence[int | float]
    level_ap_cost: int | float
    level_fatigue_cost: int | float
    climb_fatigue_cost: int | float
    max_traversible_levels: int
    fatigue_effect_mult: float
    rooted: bool = False
    stunned: bool = False


@dataclass(frozen=True)
class MovementEdge:
    source: str
    destination: str
    kind: str
    via: str | None
    ap_cost: int | float | None
    execution_fatigue_cost: int | float | None
    zoc_path_penalty: int
    resource_cost_resolved: bool


@dataclass(frozen=True)
class MovementGraphResult:
    edges: Mapping[str, tuple[MovementEdge, ...]]
    reachable: frozenset[str]
    best_resources: Mapping[str, tuple[int, int]]
    inspected_hidden_occupancy: bool


def _bb_round(value: float) -> int:
    """Mirror the positive-value rounding used by movement resource updates."""

    return int(floor(value + 0.5))


def _step_cost(
    actor: ActorMovement,
    source: Tile,
    destination: Tile,
    *,
    impassable_terrain: int,
) -> tuple[int | float, int | float] | None:
    if destination.terrain == impassable_terrain:
        return None
    if destination.terrain < 0:
        return None
    if destination.terrain >= len(actor.ap_costs):
        return None
    if destination.terrain >= len(actor.fatigue_costs):
        return None

    level_difference = destination.level - source.level
    if abs(level_difference) > actor.max_traversible_levels:
        return None

    ap = actor.ap_costs[destination.terrain]
    fatigue = actor.fatigue_costs[destination.terrain]
    if level_difference != 0:
        ap += actor.level_ap_cost
        fatigue += actor.level_fatigue_cost
        if level_difference > 0:
            fatigue += actor.climb_fatigue_cost

    if ap < 1 or fatigue < 0:
        return None
    return ap, fatigue * actor.fatigue_effect_mult


def _build_edges(
    tiles: Mapping[str, Tile],
    actor: ActorMovement,
    known_occupancy: Mapping[str, str],
    hostile_zoc_tiles: set[str],
    *,
    impassable_terrain: int,
) -> dict[str, tuple[MovementEdge, ...]]:
    edges: dict[str, tuple[MovementEdge, ...]] = {}
    for tile_id, tile in tiles.items():
        outgoing: list[MovementEdge] = []
        for direction, neighbor_id in enumerate(tile.neighbors):
            if neighbor_id is None or neighbor_id not in tiles:
                continue

            occupant = known_occupancy.get(neighbor_id)
            if occupant in {"HOSTILE", "BLOCKED"}:
                continue

            if occupant == "ALLY":
                ally_tile = tiles[neighbor_id]
                if direction >= len(ally_tile.neighbors):
                    continue
                landing_id = ally_tile.neighbors[direction]
                if landing_id is None or landing_id not in tiles:
                    continue
                if landing_id in known_occupancy:
                    continue
                landing = tiles[landing_id]
                if landing.terrain == impassable_terrain:
                    continue
                if abs(landing.level - tile.level) > actor.max_traversible_levels:
                    continue
                outgoing.append(
                    MovementEdge(
                        source=tile_id,
                        destination=landing_id,
                        kind="ALLY_JUMP",
                        via=neighbor_id,
                        ap_cost=None,
                        execution_fatigue_cost=None,
                        zoc_path_penalty=4 if tile_id in hostile_zoc_tiles else 0,
                        resource_cost_resolved=False,
                    )
                )
                continue

            step = _step_cost(
                actor,
                tile,
                tiles[neighbor_id],
                impassable_terrain=impassable_terrain,
            )
            if step is None:
                continue
            ap_cost, fatigue_cost = step
            outgoing.append(
                MovementEdge(
                    source=tile_id,
                    destination=neighbor_id,
                    kind="STEP",
                    via=None,
                    ap_cost=ap_cost,
                    execution_fatigue_cost=fatigue_cost,
                    zoc_path_penalty=4 if tile_id in hostile_zoc_tiles else 0,
                    resource_cost_resolved=True,
                )
            )
        edges[tile_id] = tuple(outgoing)
    return edges


def _dominates(left: tuple[int, int], right: tuple[int, int]) -> bool:
    left_ap, left_fatigue = left
    right_ap, right_fatigue = right
    return left_ap >= right_ap and left_fatigue <= right_fatigue


def _reachable_resources(
    edges: Mapping[str, tuple[MovementEdge, ...]],
    origin_id: str,
    actor: ActorMovement,
) -> tuple[frozenset[str], dict[str, tuple[int, int]]]:
    if actor.rooted or actor.stunned:
        return frozenset({origin_id}), {origin_id: (actor.ap, actor.fatigue)}

    labels: dict[str, list[tuple[int, int]]] = {origin_id: [(actor.ap, actor.fatigue)]}
    queue: list[tuple[str, int, int]] = [(origin_id, actor.ap, actor.fatigue)]

    while queue:
        tile_id, ap_left, fatigue = queue.pop(0)
        for edge in edges.get(tile_id, ()):
            if not edge.resource_cost_resolved:
                continue
            assert edge.ap_cost is not None
            assert edge.execution_fatigue_cost is not None
            if ap_left < edge.ap_cost:
                continue
            if fatigue + edge.execution_fatigue_cost > actor.fatigue_max:
                continue

            next_ap = _bb_round(ap_left - edge.ap_cost)
            next_fatigue = min(
                actor.fatigue_max,
                _bb_round(fatigue + edge.execution_fatigue_cost),
            )
            candidate = (next_ap, next_fatigue)
            existing = labels.setdefault(edge.destination, [])
            if any(_dominates(label, candidate) for label in existing):
                continue
            existing[:] = [
                label for label in existing if not _dominates(candidate, label)
            ]
            existing.append(candidate)
            existing.sort(key=lambda value: (-value[0], value[1]))
            queue.append((edge.destination, next_ap, next_fatigue))

    best = {
        tile_id: sorted(tile_labels, key=lambda value: (-value[0], value[1]))[0]
        for tile_id, tile_labels in labels.items()
    }
    return frozenset(labels), best


def build_movement_graph(
    tiles: Mapping[str, Tile],
    origin_id: str,
    actor: ActorMovement,
    *,
    known_occupancy: Mapping[str, str] | None = None,
    hidden_occupancy: Mapping[str, str] | None = None,
    hostile_zoc_tiles: set[str] | None = None,
    impassable_terrain: int = -1,
) -> MovementGraphResult:
    """Build player-known edges and AP/FAT reachability for one actor.

    ``hidden_occupancy`` is accepted only so tests can prove that hidden truth is
    not consulted. It is intentionally never read during graph construction.
    """

    if origin_id not in tiles:
        raise ValueError("movement origin is outside canonical topology")

    del hidden_occupancy
    occupancy = {} if known_occupancy is None else dict(known_occupancy)
    zoc = set() if hostile_zoc_tiles is None else set(hostile_zoc_tiles)
    edges = _build_edges(
        tiles,
        actor,
        occupancy,
        zoc,
        impassable_terrain=impassable_terrain,
    )
    reachable, best_resources = _reachable_resources(edges, origin_id, actor)
    return MovementGraphResult(
        edges=edges,
        reachable=reachable,
        best_resources=best_resources,
        inspected_hidden_occupancy=False,
    )
