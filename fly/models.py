from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ZoneType = Literal["normal", "blocked", "restricted", "priority"]


@dataclass(slots=True)
class Zone:
    name: str
    x: int
    y: int
    zone_type: ZoneType = "normal"
    color: str | None = None
    max_drones: int | None = None
    is_start: bool = False
    is_end: bool = False
    links: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Connection:
    left: str
    right: str
    max_link_capacity: int = 1


@dataclass(slots=True)
class MapData:
    nb_drones: int
    zones: dict[str, Zone]
    connections: list[Connection]
    start_zone: str
    end_zone: str


@dataclass(slots=True)
class Move:
    drone_id: int
    destination: str
    is_transit: bool = False