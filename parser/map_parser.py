from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


ZoneType = Literal["normal", "blocked", "restricted", "priority"]


class MapParseError(Exception):
    """Raised when the input map cannot be parsed."""


@dataclass(slots=True)
class Zone:
    """Represents a zone in the map."""

    name: str
    x: int
    y: int
    zone_type: ZoneType = "normal"
    color: str | None = None
    max_drones: int | None = None
    is_start: bool = False
    is_end: bool = False


@dataclass(slots=True)
class Connection:
    """Represents a connection between two zones."""

    left: str
    right: str
    max_link_capacity: int = 1


@dataclass(slots=True)
class MapData:
    """Parsed map data used by the simulator."""

    nb_drones: int
    zones: dict[str, Zone] = field(default_factory=dict)
    connections: list[Connection] = field(default_factory=list)
    start_zone: str | None = None
    end_zone: str | None = None


def parse_map_file(path: str | Path) -> MapData:
    """Parse a map file into a MapData structure.

    Args:
        path: Path to the map file.

    Returns:
        Parsed map data.

    Raises:
        MapParseError: If the file is invalid.
    """
    file_path = Path(path)

    try:
        raw_lines = file_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise MapParseError(f"Cannot read file '{file_path}': {exc}") from exc

    nb_drones: int | None = None
    zones: dict[str, Zone] = {}
    connections: list[Connection] = []
    start_zone: str | None = None
    end_zone: str | None = None
    seen_connections: set[tuple[str, str]] = set()

    for line_no, raw_line in enumerate(raw_lines, start=1):
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if line.startswith("nb_drones:"):
            if nb_drones is not None:
                raise MapParseError(f"Line {line_no}: duplicate nb_drones declaration")
            nb_drones = _parse_nb_drones(line, line_no)
            continue

        if line.startswith("start_hub:"):
            zone = _parse_zone_line(line, line_no, is_start=True)
            if zone.name in zones:
                raise MapParseError(f"Line {line_no}: duplicate zone '{zone.name}'")
            zones[zone.name] = zone
            start_zone = zone.name
            continue

        if line.startswith("end_hub:"):
            zone = _parse_zone_line(line, line_no, is_end=True)
            if zone.name in zones:
                raise MapParseError(f"Line {line_no}: duplicate zone '{zone.name}'")
            zones[zone.name] = zone
            end_zone = zone.name
            continue

        if line.startswith("hub:"):
            zone = _parse_zone_line(line, line_no)
            if zone.name in zones:
                raise MapParseError(f"Line {line_no}: duplicate zone '{zone.name}'")
            zones[zone.name] = zone
            continue

        if line.startswith("connection:"):
            connection = _parse_connection_line(line, line_no)
            key = tuple(sorted((connection.left, connection.right)))
            if key in seen_connections:
                raise MapParseError(
                    f"Line {line_no}: duplicate connection '{connection.left}-{connection.right}'"
                )
            seen_connections.add(key)
            connections.append(connection)
            continue

        raise MapParseError(f"Line {line_no}: unknown directive")

    if nb_drones is None:
        raise MapParseError("Missing nb_drones declaration")
    if start_zone is None:
        raise MapParseError("Missing start_hub declaration")
    if end_zone is None:
        raise MapParseError("Missing end_hub declaration")

    _validate_connections_exist(connections, zones)

    return MapData(
        nb_drones=nb_drones,
        zones=zones,
        connections=connections,
        start_zone=start_zone,
        end_zone=end_zone,
    )


def _parse_nb_drones(line: str, line_no: int) -> int:
    """Parse the nb_drones directive."""
    _, value = line.split(":", 1)
    value = value.strip()
    if not value.isdigit() or int(value) <= 0:
        raise MapParseError(f"Line {line_no}: nb_drones must be a positive integer")
    return int(value)


def _parse_zone_line(
    line: str,
    line_no: int,
    *,
    is_start: bool = False,
    is_end: bool = False,
) -> Zone:
    """Parse a hub/start/end zone line."""
    head, _, meta = line.partition("[")
    parts = head.split()

    if len(parts) < 4:
        raise MapParseError(f"Line {line_no}: invalid zone syntax")

    directive = parts[0].rstrip(":")
    name = parts[1]

    if "-" in name:
        raise MapParseError(f"Line {line_no}: zone names cannot contain dashes")

    try:
        x = int(parts[2])
        y = int(parts[3])
    except ValueError as exc:
        raise MapParseError(f"Line {line_no}: invalid coordinates") from exc

    zone_type: ZoneType = "normal"
    if directive == "start_hub" or directive == "end_hub":
        zone_type = "normal"

    metadata = _parse_metadata(meta, line_no)

    if "zone" in metadata:
        zone_value = metadata["zone"]
        if zone_value not in {"normal", "blocked", "restricted", "priority"}:
            raise MapParseError(f"Line {line_no}: invalid zone type '{zone_value}'")
        zone_type = zone_value  # type: ignore[assignment]

    max_drones: int | None = None
    if "max_drones" in metadata:
        max_drones = _parse_positive_int(metadata["max_drones"], line_no, "max_drones")

    if is_start or is_end:
        max_drones = None

    return Zone(
        name=name,
        x=x,
        y=y,
        zone_type=zone_type,
        color=metadata.get("color"),
        max_drones=max_drones,
        is_start=is_start,
        is_end=is_end,
    )


def _parse_connection_line(line: str, line_no: int) -> Connection:
    """Parse a connection line."""
    head, _, meta = line.partition("[")
    parts = head.split()

    if len(parts) < 2:
        raise MapParseError(f"Line {line_no}: invalid connection syntax")

    raw = parts[1]
    if "-" not in raw:
        raise MapParseError(f"Line {line_no}: invalid connection format")

    left, right = raw.split("-", 1)
    metadata = _parse_metadata(meta, line_no)

    max_link_capacity = 1
    if "max_link_capacity" in metadata:
        max_link_capacity = _parse_positive_int(
            metadata["max_link_capacity"],
            line_no,
            "max_link_capacity",
        )

    return Connection(left=left, right=right, max_link_capacity=max_link_capacity)


def _parse_metadata(meta: str, line_no: int) -> dict[str, str]:
    """Parse metadata inside square brackets."""
    meta = meta.strip()
    if not meta:
        return {}

    if meta.endswith("]"):
        meta = meta[:-1].strip()
    items = meta.split()

    result: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise MapParseError(f"Line {line_no}: invalid metadata token '{item}'")
        key, value = item.split("=", 1)
        result[key.strip()] = value.strip()

    return result


def _parse_positive_int(value: str, line_no: int, field_name: str) -> int:
    """Parse a positive integer field."""
    if not value.isdigit() or int(value) <= 0:
        raise MapParseError(f"Line {line_no}: {field_name} must be a positive integer")
    return int(value)


def _validate_connections_exist(connections: list[Connection], zones: dict[str, Zone]) -> None:
    """Ensure every connection references known zones."""
    for connection in connections:
        if connection.left not in zones:
            raise MapParseError(f"Unknown zone '{connection.left}' in connection")
        if connection.right not in zones:
            raise MapParseError(f"Unknown zone '{connection.right}' in connection")