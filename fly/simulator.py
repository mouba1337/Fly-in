from __future__ import annotations

import heapq
from collections.abc import Iterator
from dataclasses import dataclass

from fly.models import DroneState, MapData, Move, Zone


@dataclass(slots=True)
class PathCandidate:
    """A candidate path with a cost score."""

    path: list[str]
    score: int


class Simulator:
    """Turn-based drone scheduler."""

    def run(self, data: MapData) -> Iterator[list[Move]]:
        """Yield simulation turns until all drones are delivered."""
        graph = self._build_graph(data)
        candidates = self._build_candidate_paths(data, graph)

        if not candidates:
            raise ValueError("No valid path from start to end")

        drones = self._assign_drones(data, candidates)
        delivered = 0

        while delivered < data.nb_drones:
            turn_moves: list[Move] = []
            zone_occupied: dict[str, int] = {}
            edge_occupied: dict[tuple[str, str], int] = {}

            for drone in drones:
                if drone.delivered or drone.transit_remaining <= 0:
                    continue

                drone.transit_remaining -= 1
                if drone.transit_remaining > 0:
                    continue

                next_zone = drone.path[drone.path_index + 1]
                if not self._can_enter_zone(data, next_zone, zone_occupied):
                    drone.transit_remaining = 1
                    continue

                connection_name = self._connection_name(data, drone.current_zone, next_zone)
                self._advance_drone(drone, next_zone)
                zone_occupied[next_zone] = zone_occupied.get(next_zone, 0) + 1

                turn_moves.append(
                    Move(
                        drone_id=drone.drone_id,
                        destination=next_zone,
                        destination_type=data.zones[next_zone].zone_type,
                        is_transit=False,
                        connection_name=connection_name,
                    )
                )

                if next_zone == data.end_zone:
                    drone.delivered = True
                    delivered += 1

            for drone in drones:
                if drone.delivered or drone.transit_remaining > 0:
                    continue

                if drone.path_index >= len(drone.path) - 1:
                    continue

                current_zone = drone.current_zone
                next_zone = drone.path[drone.path_index + 1]
                edge_key = tuple(sorted((current_zone, next_zone)))

                if not self._can_use_edge(data, current_zone, next_zone, edge_occupied):
                    continue
                if not self._can_enter_zone(data, next_zone, zone_occupied):
                    continue

                next_zone_obj = data.zones[next_zone]
                edge_occupied[edge_key] = edge_occupied.get(edge_key, 0) + 1

                if next_zone_obj.zone_type == "restricted":
                    drone.transit_remaining = 1
                    connection_name = self._connection_name(data, current_zone, next_zone)
                    turn_moves.append(
                        Move(
                            drone_id=drone.drone_id,
                            destination=next_zone,
                            destination_type=next_zone_obj.zone_type,
                            is_transit=True,
                            connection_name=connection_name,
                        )
                    )
                else:
                    self._advance_drone(drone, next_zone)
                    zone_occupied[next_zone] = zone_occupied.get(next_zone, 0) + 1
                    turn_moves.append(
                        Move(
                            drone_id=drone.drone_id,
                            destination=next_zone,
                            destination_type=next_zone_obj.zone_type,
                            is_transit=False,
                            connection_name=None,
                        )
                    )

                    if next_zone == data.end_zone:
                        drone.delivered = True
                        delivered += 1

            if turn_moves:
                yield turn_moves

    def _assign_drones(self, data: MapData, candidates: list[PathCandidate]) -> list[DroneState]:
        """Assign drones round-robin across candidate paths."""
        drones: list[DroneState] = []
        paths = [candidate.path for candidate in candidates]

        for index in range(data.nb_drones):
            drones.append(
                DroneState(
                    drone_id=index + 1,
                    current_zone=data.start_zone,
                    path=paths[index % len(paths)],
                )
            )
        return drones

    def _build_graph(self, data: MapData) -> dict[str, list[str]]:
        """Build adjacency list."""
        graph: dict[str, list[str]] = {name: [] for name in data.zones}
        for connection in data.connections:
            graph[connection.left].append(connection.right)
            graph[connection.right].append(connection.left)
        return graph

    def _build_candidate_paths(
        self,
        data: MapData,
        graph: dict[str, list[str]],
    ) -> list[PathCandidate]:
        """Build candidate paths."""
        base = self._dijkstra(data, graph)
        if not base:
            return []

        candidates = [PathCandidate(path=base, score=self._path_score(data, base))]
        avoided_edges: set[tuple[str, str]] = {
            tuple(sorted((base[i], base[i + 1])))
            for i in range(len(base) - 1)
        }

        for _ in range(3):
            alt = self._dijkstra(data, graph, avoided_edges=avoided_edges)
            if not alt:
                break
            if alt not in [c.path for c in candidates]:
                candidates.append(PathCandidate(path=alt, score=self._path_score(data, alt)))
                for i in range(len(alt) - 1):
                    avoided_edges.add(tuple(sorted((alt[i], alt[i + 1]))))

        candidates.sort(key=lambda c: (c.score, len(c.path)))
        return candidates

    def _dijkstra(
        self,
        data: MapData,
        graph: dict[str, list[str]],
        avoided_edges: set[tuple[str, str]] | None = None,
    ) -> list[str]:
        """Find a weighted shortest path."""
        avoided_edges = avoided_edges or set()
        start = data.start_zone
        goal = data.end_zone

        dist: dict[str, int] = {start: 0}
        prev: dict[str, str | None] = {start: None}
        heap: list[tuple[int, str]] = [(0, start)]

        while heap:
            current_cost, current = heapq.heappop(heap)
            if current_cost != dist.get(current):
                continue
            if current == goal:
                break

            for neighbor in graph[current]:
                if data.zones[neighbor].zone_type == "blocked":
                    continue

                edge_key = tuple(sorted((current, neighbor)))
                if edge_key in avoided_edges and current != start:
                    continue

                new_cost = current_cost + self._zone_cost(data.zones[neighbor])
                if neighbor not in dist or new_cost < dist[neighbor]:
                    dist[neighbor] = new_cost
                    prev[neighbor] = current
                    heapq.heappush(heap, (new_cost, neighbor))

        if goal not in prev:
            return []

        path: list[str] = []
        node: str | None = goal
        while node is not None:
            path.append(node)
            node = prev[node]
        path.reverse()
        return path

    def _path_score(self, data: MapData, path: list[str]) -> int:
        """Score a path."""
        score = 0
        for node in path:
            zone = data.zones[node]
            score += self._zone_cost(zone)
            if zone.zone_type == "priority":
                score -= 1
        return score

    def _zone_cost(self, zone: Zone) -> int:
        """Return movement cost for a zone."""
        if zone.zone_type == "restricted":
            return 2
        return 1

    def _can_use_edge(
        self,
        data: MapData,
        left: str,
        right: str,
        edge_occupied: dict[tuple[str, str], int],
    ) -> bool:
        """Check connection capacity."""
        cap = self._edge_capacity(data, left, right)
        key = tuple(sorted((left, right)))
        return edge_occupied.get(key, 0) < cap

    def _edge_capacity(self, data: MapData, left: str, right: str) -> int:
        """Return the edge capacity."""
        for connection in data.connections:
            if {connection.left, connection.right} == {left, right}:
                return connection.max_link_capacity
        return 1

    def _can_enter_zone(
        self,
        data: MapData,
        zone_name: str,
        zone_occupied: dict[str, int],
    ) -> bool:
        """Check zone capacity."""
        if zone_name == data.start_zone or zone_name == data.end_zone:
            return True

        zone = data.zones[zone_name]
        return zone_occupied.get(zone_name, 0) < zone.max_drones

    def _advance_drone(self, drone: DroneState, zone_name: str) -> None:
        """Advance drone state."""
        drone.current_zone = zone_name
        drone.path_index += 1

    def _connection_name(self, data: MapData, left: str, right: str) -> str | None:
        """Return the connection name between two zones."""
        for connection in data.connections:
            if {connection.left, connection.right} == {left, right}:
                return f"{connection.left}-{connection.right}"
        return None