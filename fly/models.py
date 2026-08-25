from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ZoneType = Literal["normal", "blocked", "restricted", "priority"]


@dataclass(slots=True)
class Zone:
    """A zone node in the drone network."""

    name: str
    x: int
    y: int
    zone_type: ZoneType = "normal"
    color: str | None = None
    max_drones: int = 1
    is_start: bool = False
    is_end: bool = False


@dataclass(slots=True)
class Connection:
    """A bidirectional connection between two zones."""

    left: str
    right: str
    max_link_capacity: int = 1


@dataclass(slots=True)
class MapData:
    """Parsed input map data."""

    nb_drones: int
    zones: dict[str, Zone]
    connections: list[Connection]
    start_zone: str
    end_zone: str


@dataclass(slots=True)
class Move:
    """One movement emitted during a simulation turn."""

    drone_id: int
    destination: str
    destination_type: ZoneType
    is_transit: bool = False
    connection_name: str | None = None


@dataclass(slots=True)
class DroneState:
    """Runtime state for a drone during simulation."""

    drone_id: int
    current_zone: str
    path: list[str]
    path_index: int = 0
    transit_remaining: int = 0
    delivered: bool = False
