from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field

from fly.exceptions import SimulationError
from fly.models import MapData, Move


@dataclass(slots=True)
class Timeline:
    """Tracks future occupancy for a zone or a connection, turn by turn."""

    capacity: int
    occupancy: list[int] = field(default_factory=list)

    def can_enter(self, turn: int) -> bool:
        """Return True if one more drone fits at ``turn``."""
        # -1 represents infinite capacity (start and end hubs).
        if self.capacity == -1:
            return True
        self._ensure_size(turn)
        return self.occupancy[turn] < self.capacity

    def reserve(self, turn: int) -> None:
        """Book one slot at ``turn``."""
        if self.capacity == -1:
            return
        self._ensure_size(turn)
        self.occupancy[turn] += 1

    def _ensure_size(self, turn: int) -> None:
        """Grow the occupancy list so that ``turn`` is a valid index."""
        if turn >= len(self.occupancy):
            self.occupancy.extend([0] * (turn - len(self.occupancy) + 1))


class SpaceTimeGraph:
    """The zone network plus the reservation table used to avoid conflicts."""

    def __init__(self, data: MapData) -> None:
        self.data = data
        self.zone_timelines: dict[str, Timeline] = {}
        self.edge_timelines: dict[tuple[str, str], Timeline] = {}
        self.adj: dict[str, list[str]] = {name: [] for name in data.zones}

        self._initialize_timelines()

    def _initialize_timelines(self) -> None:
        """Build the adjacency lists and one Timeline per zone and per edge."""
        for name, zone in self.data.zones.items():
            if zone.is_start or zone.is_end:
                # max_drones is ignored on the start and end hubs.
                self.zone_timelines[name] = Timeline(capacity=-1)
            else:
                self.zone_timelines[name] = Timeline(capacity=zone.max_drones)

        for conn in self.data.connections:
            self.adj[conn.left].append(conn.right)
            self.adj[conn.right].append(conn.left)
            key = self.edge_key(conn.left, conn.right)
            self.edge_timelines[key] = Timeline(capacity=conn.max_link_capacity)

    @staticmethod
    def edge_key(left: str, right: str) -> tuple[str, str]:
        """Return a direction-independent key for a connection."""
        return (left, right) if left <= right else (right, left)

    def travel_cost(self, zone_name: str) -> int:
        """Return how many turns it takes to reach ``zone_name``."""
        return 2 if self.data.zones[zone_name].zone_type == "restricted" else 1

    def is_move_valid(self, current: str, nxt: str, current_turn: int) -> bool:
        """Return True if a drone may leave ``current`` for ``nxt`` now.

        The whole move is checked up front, including the landing turn, so a
        drone never enters a connection it could not leave on time.
        """
        if self.data.zones[nxt].zone_type == "blocked":
            return False

        cost = self.travel_cost(nxt)
        key = self.edge_key(current, nxt)

        # The drone occupies the connection for the whole transit, so every
        # turn it spends in flight must have room on that link.
        for offset in range(cost):
            if not self.edge_timelines[key].can_enter(current_turn + offset):
                return False

        return self.zone_timelines[nxt].can_enter(current_turn + cost)

    def reserve_move(self, current: str, nxt: str, current_turn: int) -> None:
        """Book the connection and the destination zone for one drone."""
        cost = self.travel_cost(nxt)
        key = self.edge_key(current, nxt)

        for offset in range(cost):
            self.edge_timelines[key].reserve(current_turn + offset)
        self.zone_timelines[nxt].reserve(current_turn + cost)


@dataclass(frozen=True, slots=True)
class Position:
    """Where a drone is: inside a zone, or in flight on a connection.

    ``origin`` is None once the drone has landed. When it is set, the drone is
    still on the connection coming from ``origin`` and heading for ``zone``.
    """

    zone: str
    origin: str | None = None

    @property
    def in_flight(self) -> bool:
        """Return True while the drone is still on a connection."""
        return self.origin is not None


@dataclass(slots=True)
class StateNode:
    """One node of the space-time search: a position at a given turn."""

    position: Position
    turn: int
    path: list[tuple[str, int]]


class Simulator:
    """Prioritized space-time planner: drones are routed one after another."""

    def run(self, data: MapData) -> Iterator[list[Move]]:
        """Route every drone and yield the moves of each simulation turn."""
        graph = SpaceTimeGraph(data)

        if data.start_zone not in self._zones_reaching_goal(graph, data):
            raise SimulationError(
                f"No route exists from '{data.start_zone}' " f"to '{data.end_zone}'"
            )

        neighbors = self._rank_neighbors(graph, data)

        schedules: dict[int, list[tuple[str, int]]] = {}
        for drone_id in range(1, data.nb_drones + 1):
            path = self._find_path_for_drone(graph, data, neighbors)
            if not path:
                raise SimulationError(f"No valid path found for drone {drone_id}")
            schedules[drone_id] = path

        yield from self._transpose_to_turns(schedules, data)

    def _zones_reaching_goal(self, graph: SpaceTimeGraph, data: MapData) -> set[str]:
        """Every zone with at least one route to the end hub.

        Used only to reject a map whose goal cannot be reached at all, with a
        clear message instead of an exhausted search.
        """
        seen = {data.end_zone}
        queue: deque[str] = deque([data.end_zone])

        while queue:
            current = queue.popleft()
            for neighbor in graph.adj[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)

        return seen

    def _rank_neighbors(
        self, graph: SpaceTimeGraph, data: MapData
    ) -> dict[str, list[str]]:
        """Pre-sort each zone's neighbours, priority zones first.

        A state is claimed the first time it is queued, so exploring priority
        neighbours first is what makes them preferred when two routes would
        arrive on the same turn. The order depends only on the map, so it is
        computed once here rather than on every expanded state.
        """

        def is_priority(name: str) -> int:
            return 0 if data.zones[name].zone_type == "priority" else 1

        return {zone: sorted(graph.adj[zone], key=is_priority) for zone in data.zones}

    def _find_path_for_drone(
        self,
        graph: SpaceTimeGraph,
        data: MapData,
        neighbors: dict[str, list[str]],
    ) -> list[tuple[str, int]]:
        """Find the earliest-arrival path that respects every reservation.

        The search runs over (position, turn) states with a FIFO queue. That is
        only correct when every transition costs the same, and reaching a
        restricted zone costs 2 turns -- so a restricted move is split into two
        one-turn steps through an explicit in-flight position on the
        connection. Every transition then advances the clock by exactly one
        turn, the queue stays sorted by turn, and the first time the goal is
        popped it is with the smallest possible arrival turn.

        Modelling the connection as a real state also enforces the rule that a
        drone may not linger on it: an in-flight position has exactly one
        successor, landing on the next turn.
        """
        start = data.start_zone
        goal = data.end_zone

        origin = Position(start)
        queue: deque[StateNode] = deque([StateNode(origin, 0, [(start, 0)])])
        visited: set[tuple[Position, int]] = {(origin, 0)}

        # Safety horizon: waiting in the unlimited start hub is always
        # possible, so without it an unreachable goal would loop forever.
        horizon = len(data.zones) * (data.nb_drones + 2) + 2

        while queue:
            current = queue.popleft()
            turn = current.turn + 1

            # Every transition costs one turn, so the queue is sorted by turn:
            # once we pass the horizon, everything left is past it too.
            if current.turn > horizon:
                break

            # A drone in flight has exactly one legal next step: landing.
            if current.position.in_flight:
                landed = Position(current.position.zone)
                if (landed, turn) not in visited:
                    visited.add((landed, turn))
                    queue.append(
                        StateNode(landed, turn, current.path + [(landed.zone, turn)])
                    )
                continue

            zone = current.position.zone
            if zone == goal:
                self._lock_reservations(graph, current.path)
                return current.path

            for neighbor in neighbors[zone]:
                if not graph.is_move_valid(zone, neighbor, current.turn):
                    continue

                if graph.travel_cost(neighbor) == 2:
                    # Enter the connection now, land on the following turn.
                    # The waypoint is recorded only once the drone lands.
                    nxt = Position(neighbor, origin=zone)
                    path = current.path
                else:
                    nxt = Position(neighbor)
                    path = current.path + [(neighbor, turn)]

                if (nxt, turn) not in visited:
                    visited.add((nxt, turn))
                    queue.append(StateNode(nxt, turn, path))

            # Wait in place. Only waiting on a connection is forbidden, and an
            # in-flight position never reaches here: it is forced to land.
            if (current.position, turn) not in visited:
                if graph.zone_timelines[zone].can_enter(turn):
                    visited.add((current.position, turn))
                    queue.append(
                        StateNode(current.position, turn, current.path + [(zone, turn)])
                    )

        return []

    def _lock_reservations(
        self, graph: SpaceTimeGraph, path: list[tuple[str, int]]
    ) -> None:
        """Book every zone and connection used by an accepted path."""
        for index in range(len(path) - 1):
            zone, turn = path[index]
            next_zone, _ = path[index + 1]

            if zone == next_zone:
                graph.zone_timelines[zone].reserve(turn + 1)
            else:
                graph.reserve_move(zone, next_zone, turn)

    def _transpose_to_turns(
        self, schedules: dict[int, list[tuple[str, int]]], data: MapData
    ) -> Iterator[list[Move]]:
        """Turn per-drone paths into one list of moves per simulation turn."""
        actions: dict[int, dict[int, Move]] = {d: {} for d in schedules}

        for drone_id, path in schedules.items():
            for index in range(len(path) - 1):
                zone, turn = path[index]
                next_zone, _ = path[index + 1]

                if zone == next_zone:
                    # Waiting drones are omitted from the output.
                    continue

                dest_type = data.zones[next_zone].zone_type

                if dest_type == "restricted":
                    link = self._connection_name(data, zone, next_zone)
                    # Turn 1: enter the connection.
                    actions[drone_id][turn] = Move(
                        drone_id=drone_id,
                        destination=next_zone,
                        destination_type=dest_type,
                        is_transit=True,
                        connection_name=link,
                    )
                    # Turn 2: land in the restricted zone.
                    actions[drone_id][turn + 1] = Move(
                        drone_id=drone_id,
                        destination=next_zone,
                        destination_type=dest_type,
                        is_transit=False,
                        connection_name=link,
                    )
                else:
                    actions[drone_id][turn] = Move(
                        drone_id=drone_id,
                        destination=next_zone,
                        destination_type=dest_type,
                        is_transit=False,
                        connection_name=None,
                    )

        last_turn = max(
            (max(moves, default=-1) for moves in actions.values()),
            default=-1,
        )

        for turn in range(last_turn + 1):
            # A turn where every drone waits is still a turn: it is yielded as
            # an empty line so the turn count stays exact.
            yield [
                actions[drone_id][turn]
                for drone_id in sorted(actions)
                if turn in actions[drone_id]
            ]

    def _connection_name(self, data: MapData, left: str, right: str) -> str | None:
        """Return the declared name of the connection between two zones."""
        for connection in data.connections:
            if {connection.left, connection.right} == {left, right}:
                return f"{connection.left}-{connection.right}"
        return None
