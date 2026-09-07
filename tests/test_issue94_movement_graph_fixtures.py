from __future__ import annotations

from bb_agent.movement_graph import ActorMovement, Tile, build_movement_graph


def _line_tiles(
    *, terrain: tuple[int, ...] = (1, 1, 1), levels=(0, 0, 0)
):
    tiles = {
        "a": Tile("a", terrain[0], levels[0], ("b", None, None, None, None, None)),
        "b": Tile("b", terrain[1], levels[1], ("c", None, None, "a", None, None)),
        "c": Tile("c", terrain[2], levels[2], (None, None, None, "b", None, None)),
    }
    return tiles


def _actor(**overrides: object) -> ActorMovement:
    values: dict[str, object] = {
        "ap": 9,
        "fatigue": 0,
        "fatigue_max": 100,
        "ap_costs": (1, 2, 2, 3, 3, 4, 4, 2, 4),
        "fatigue_costs": (0, 2, 4, 6, 6, 8, 14, 6, 12),
        "level_ap_cost": 1,
        "level_fatigue_cost": 4,
        "climb_fatigue_cost": 2,
        "max_traversible_levels": 1,
        "fatigue_effect_mult": 1.0,
        "rooted": False,
        "stunned": False,
    }
    values.update(overrides)
    return ActorMovement(**values)


def test_flat_adjacent_empty_move_is_reachable() -> None:
    graph = build_movement_graph(_line_tiles(), "a", _actor())
    assert "b" in graph.reachable
    assert graph.best_resources["b"] == (7, 2)


def test_impassable_and_excessive_elevation_are_rejected() -> None:
    impassable = _line_tiles(terrain=(1, -1, 1))
    assert "b" not in build_movement_graph(impassable, "a", _actor()).reachable

    too_high = _line_tiles(levels=(0, 2, 2))
    assert "b" not in build_movement_graph(too_high, "a", _actor()).reachable


def test_max_elevation_and_mixed_terrain_costs_use_actor_tables() -> None:
    tiles = _line_tiles(terrain=(1, 2, 3), levels=(0, 1, 1))
    graph = build_movement_graph(tiles, "a", _actor())
    assert graph.best_resources["b"] == (6, 10)
    assert graph.best_resources["c"] == (3, 16)


def test_actor_modified_tables_are_authoritative() -> None:
    actor = _actor(
        ap_costs=(1, 1, 1, 1, 1, 1, 1, 1, 1),
        fatigue_costs=(0, 1, 1, 1, 1, 1, 1, 1, 1),
    )
    graph = build_movement_graph(_line_tiles(), "a", actor)
    assert graph.best_resources["c"] == (7, 2)


def test_ap_and_fatigue_limits_prune_only_unaffordable_routes() -> None:
    assert (
        "c" not in build_movement_graph(_line_tiles(), "a", _actor(ap=3)).reachable
    )
    assert (
        "b"
        not in build_movement_graph(
            _line_tiles(), "a", _actor(fatigue=99, fatigue_max=100)
        ).reachable
    )


def test_resource_reachability_accepts_any_feasible_route() -> None:
    tiles = {
        "o": Tile("o", 1, 0, ("cheap_ap", "cheap_fat", None, None, None, None)),
        "cheap_ap": Tile("cheap_ap", 2, 0, ("d", None, None, "o", None, None)),
        "cheap_fat": Tile("cheap_fat", 1, 0, (None, "d", None, None, "o", None)),
        "d": Tile("d", 1, 0, (None, None, None, "cheap_ap", "cheap_fat", None)),
    }
    actor = _actor(ap=5, fatigue=95, fatigue_max=100)
    graph = build_movement_graph(tiles, "o", actor)
    assert "d" in graph.reachable
    assert graph.best_resources["d"] == (1, 99)


def test_one_ally_jump_topology_is_legal_but_resource_cost_stays_unresolved() -> None:
    graph = build_movement_graph(
        _line_tiles(), "a", _actor(), known_occupancy={"b": "ALLY"}
    )
    jumps = [edge for edge in graph.edges["a"] if edge.kind == "ALLY_JUMP"]
    assert [(edge.via, edge.destination) for edge in jumps] == [("b", "c")]
    assert jumps[0].resource_cost_resolved is False
    assert "c" not in graph.reachable


def test_blocked_or_enemy_landing_prevents_ally_jump() -> None:
    blocked = build_movement_graph(
        _line_tiles(),
        "a",
        _actor(),
        known_occupancy={"b": "ALLY", "c": "BLOCKED"},
    )
    assert not [edge for edge in blocked.edges["a"] if edge.kind == "ALLY_JUMP"]

    hostile = build_movement_graph(
        _line_tiles(),
        "a",
        _actor(),
        known_occupancy={"b": "HOSTILE"},
    )
    assert hostile.edges["a"] == ()


def test_two_consecutive_allies_cannot_be_crossed_as_one_jump() -> None:
    tiles = _line_tiles()
    graph = build_movement_graph(
        tiles,
        "a",
        _actor(),
        known_occupancy={"b": "ALLY", "c": "ALLY"},
    )
    assert not [edge for edge in graph.edges["a"] if edge.kind == "ALLY_JUMP"]


def test_landing_then_later_jump_is_two_distinct_transitions() -> None:
    tiles = {
        "a": Tile("a", 1, 0, ("b", None, None, None, None, None)),
        "b": Tile("b", 1, 0, ("c", None, None, "a", None, None)),
        "c": Tile("c", 1, 0, ("d", None, None, "b", None, None)),
        "d": Tile("d", 1, 0, ("e", None, None, "c", None, None)),
        "e": Tile("e", 1, 0, (None, None, None, "d", None, None)),
    }
    graph = build_movement_graph(
        tiles,
        "a",
        _actor(),
        known_occupancy={"b": "ALLY", "d": "ALLY"},
    )
    first = {
        (edge.via, edge.destination)
        for edge in graph.edges["a"]
        if edge.kind == "ALLY_JUMP"
    }
    later = {
        (edge.via, edge.destination)
        for edge in graph.edges["c"]
        if edge.kind == "ALLY_JUMP"
    }
    assert ("b", "c") in first
    assert ("d", "e") in later


def test_hidden_occupant_is_absent_from_player_known_graph() -> None:
    graph = build_movement_graph(
        _line_tiles(),
        "a",
        _actor(),
        known_occupancy={},
        hidden_occupancy={"b": "HOSTILE"},
    )
    assert "b" in graph.reachable
    assert graph.inspected_hidden_occupancy is False


def test_zoc_penalty_attaches_to_exit_not_entry() -> None:
    graph = build_movement_graph(
        _line_tiles(), "a", _actor(), hostile_zoc_tiles={"b"}
    )
    enter = next(edge for edge in graph.edges["a"] if edge.destination == "b")
    leave = next(edge for edge in graph.edges["b"] if edge.destination == "c")
    assert enter.zoc_path_penalty == 0
    assert leave.zoc_path_penalty == 4


def test_rooted_or_stunned_actor_has_no_movement_reachability() -> None:
    assert build_movement_graph(_line_tiles(), "a", _actor(rooted=True)).reachable == {
        "a"
    }
    assert build_movement_graph(_line_tiles(), "a", _actor(stunned=True)).reachable == {
        "a"
    }


def test_canonical_adjacency_order_is_deterministic() -> None:
    graph = build_movement_graph(_line_tiles(), "a", _actor())
    assert tuple(edge.destination for edge in graph.edges["a"]) == ("b",)
