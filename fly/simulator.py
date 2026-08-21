from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field

from fly.models import MapData, Move


@dataclass(slots=True)
class Timeline:
    """Tracks future occupancy for a zone or edge using a flat list."""
    capacity: int
    occupancy: list[int] = field(default_factory=list)

    def can_enter(self, turn: int) -> bool:
        # -1 represents infinite capacity (start and end hubs)
        if self.capacity == -1:
            return True
        self._ensure_size(turn)
        return self.occupancy[turn] < self.capacity

    def reserve(self, turn: int) -> None:
        if self.capacity == -1:
            return
        self._ensure_size(turn)
        self.occupancy[turn] += 1

    def _ensure_size(self, turn: int) -> None:
        if turn >= len(self.occupancy):
            self.occupancy.extend([0] * (turn - len(self.occupancy) + 1))


class SpaceTimeGraph:
    """Manages the network and time-based reservations."""
    
    def __init__(self, data: MapData):
        self.data = data
        self.zone_timelines: dict[str, Timeline] = {}
        self.edge_timelines: dict[tuple[str, str], Timeline] = {}
        self.adj: dict[str, list[str]] = {name: [] for name in data.zones}
        
        self._initialize_timelines()

    def _initialize_timelines(self) -> None:
        for name, zone in self.data.zones.items():
            if name in (self.data.start_zone, self.data.end_zone):
                self.zone_timelines[name] = Timeline(capacity=-1)
            else:
                self.zone_timelines[name] = Timeline(capacity=zone.max_drones or 1)

        for conn in self.data.connections:
            self.adj[conn.left].append(conn.right)
            self.adj[conn.right].append(conn.left)
            
            edge_key = tuple(sorted((conn.left, conn.right)))
            self.edge_timelines[edge_key] = Timeline(capacity=conn.max_link_capacity)

    def is_move_valid(self, current: str, nxt: str, current_turn: int) -> bool:
        target_zone = self.data.zones[nxt]
        if target_zone.zone_type == "blocked":
            return False

        travel_cost = 2 if target_zone.zone_type == "restricted" else 1
        arrival_turn = current_turn + travel_cost

        edge_key = tuple(sorted((current, nxt)))
        if not self.edge_timelines[edge_key].can_enter(current_turn):
            return False

        if not self.zone_timelines[nxt].can_enter(arrival_turn):
            return False

        return True

    def reserve_move(self, current: str, nxt: str, current_turn: int) -> None:
        target_zone = self.data.zones[nxt]
        travel_cost = 2 if target_zone.zone_type == "restricted" else 1
        arrival_turn = current_turn + travel_cost

        edge_key = tuple(sorted((current, nxt)))
        self.edge_timelines[edge_key].reserve(current_turn)
        self.zone_timelines[nxt].reserve(arrival_turn)


@dataclass(slots=True)
class StateNode:
    zone_name: str
    turn: int
    path: list[tuple[str, int]]


class Simulator:
    """Turn-based drone scheduler using Space-Time BFS."""

    def run(self, data: MapData) -> Iterator[list[Move]]:
        st_graph = SpaceTimeGraph(data)

        # --- Compute topological distances to the goal ---
        distances = {data.end_zone: 0}
        bfs_queue = deque([data.end_zone])
        while bfs_queue:
            curr = bfs_queue.popleft()
            for neighbor in st_graph.adj[curr]:
                if neighbor not in distances:
                    distances[neighbor] = distances[curr] + 1
                    bfs_queue.append(neighbor)
        # -------------------------------------------------------

        drone_schedules: dict[int, list[tuple[str, int]]] = {}

        # 1. Route each drone individually from Start to Finish
        for drone_id in range(1, data.nb_drones + 1):
            
            # --- THE FIX IS HERE: We added `distances` as the third argument ---
            schedule = self._find_path_for_drone(st_graph, data, distances)
            
            if not schedule:
                raise ValueError(f"No valid path found for drone {drone_id}")
            drone_schedules[drone_id] = schedule

        # 2. Transpose schedules into turn-by-turn output for the Iterator
        yield from self._transpose_to_turns(drone_schedules, data)

    def _find_path_for_drone(
        self, graph: SpaceTimeGraph, data: MapData, distances: dict[str, int]
    ) -> list[tuple[str, int]]:
        start = data.start_zone
        if start is None:
            return []
            
        goal = data.end_zone
        
        # Queue stores: StateNode(zone, turn, history)
        queue: deque[StateNode] = deque([StateNode(start, 0, [(start, 0)])])
        visited: set[tuple[str, int]] = {(start, 0)}

        while queue:
            current = queue.popleft()

            if current.zone_name == goal:
                # We found the fastest valid path! Reserve it globally.
                self._lock_reservations(graph, current.path)
                return current.path

            # Group neighbors by flow direction toward the goal
            forward = []
            backward = []
            for neighbor in graph.adj[current.zone_name]:
                if distances[neighbor] < distances[current.zone_name]:
                    forward.append(neighbor)
                else:
                    backward.append(neighbor)

            # Option 1: Move FORWARD (Highest Priority)
            for neighbor in forward:
                if graph.is_move_valid(current.zone_name, neighbor, current.turn):
                    target_zone = data.zones[neighbor]
                    travel_cost = 2 if target_zone.zone_type == "restricted" else 1
                    arrival_turn = current.turn + travel_cost
                    
                    next_state = (neighbor, arrival_turn)
                    if next_state not in visited:
                        visited.add(next_state)
                        new_path = current.path + [next_state]
                        queue.append(StateNode(neighbor, arrival_turn, new_path))

            # Option 2: WAIT in place (If forward is blocked)
            if data.zones[current.zone_name].zone_type != "restricted":
                if graph.zone_timelines[current.zone_name].can_enter(current.turn + 1):
                    wait_state = (current.zone_name, current.turn + 1)
                    if wait_state not in visited:
                        visited.add(wait_state)
                        new_path = current.path + [wait_state]
                        queue.append(StateNode(current.zone_name, current.turn + 1, new_path))

            # Option 3: Move BACKWARD / LATERAL (Last resort to escape traffic)
            for neighbor in backward:
                if graph.is_move_valid(current.zone_name, neighbor, current.turn):
                    target_zone = data.zones[neighbor]
                    travel_cost = 2 if target_zone.zone_type == "restricted" else 1
                    arrival_turn = current.turn + travel_cost
                    
                    next_state = (neighbor, arrival_turn)
                    if next_state not in visited:
                        visited.add(next_state)
                        new_path = current.path + [next_state]
                        queue.append(StateNode(neighbor, arrival_turn, new_path))

        return []

    def _lock_reservations(self, graph: SpaceTimeGraph, path: list[tuple[str, int]]) -> None:
        """Iterate through the found path and reserve the timelines."""
        for i in range(len(path) - 1):
            curr_zone, curr_turn = path[i]
            next_zone, _ = path[i + 1]
            
            # If the drone waited, reserve the zone. Otherwise, reserve the move edge.
            if curr_zone == next_zone:
                graph.zone_timelines[curr_zone].reserve(curr_turn + 1)
            else:
                graph.reserve_move(curr_zone, next_zone, curr_turn)

    def _transpose_to_turns(self, schedules: dict[int, list[tuple[str, int]]], data: MapData) -> Iterator[list[Move]]:
        """Converts internal path schedules back into turn-by-turn simulation yields."""
        drone_actions: dict[int, dict[int, Move]] = {d: {} for d in schedules}
        
        # Build a dictionary of actions indexed by drone_id and turn number
        for drone_id, path in schedules.items():
            for i in range(len(path) - 1):
                curr_zone, curr_turn = path[i]
                next_zone, next_turn = path[i + 1]

                # Drone is just waiting in place; no Move yielded
                if curr_zone == next_zone:
                    continue 

                dest_type = data.zones[next_zone].zone_type

                if dest_type == "restricted":
                    conn_name = self._connection_name(data, curr_zone, next_zone)
                    # Turn 1: Enter the connection (is_transit = True)
                    drone_actions[drone_id][curr_turn] = Move(
                        drone_id=drone_id,
                        destination=next_zone,
                        destination_type=dest_type,
                        is_transit=True,
                        connection_name=conn_name
                    )
                    # Turn 2: Arrive at destination (is_transit = False)
                    drone_actions[drone_id][curr_turn + 1] = Move(
                        drone_id=drone_id,
                        destination=next_zone,
                        destination_type=dest_type,
                        is_transit=False,
                        connection_name=conn_name
                    )
                else:
                    # Turn 1: Arrive directly
                    drone_actions[drone_id][curr_turn] = Move(
                        drone_id=drone_id,
                        destination=next_zone,
                        destination_type=dest_type,
                        is_transit=False,
                        connection_name=None
                    )

        max_turn = max((max(actions.keys(), default=-1) for actions in drone_actions.values()), default=-1)
        
        # Yield the moves turn by turn exactly as the CLI/Printer expects
        for t in range(max_turn + 1):
            turn_moves = []
            for drone_id in sorted(drone_actions.keys()):
                if t in drone_actions[drone_id]:
                    turn_moves.append(drone_actions[drone_id][t])
            
            if turn_moves:
                yield turn_moves

    def _connection_name(self, data: MapData, left: str, right: str) -> str | None:
        """Helper to find the connection name between two zones."""
        for connection in data.connections:
            if {connection.left, connection.right} == {left, right}:
                return f"{connection.left}-{connection.right}"
        return None