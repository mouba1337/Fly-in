from __future__ import annotations

from pathlib import Path

from fly.exceptions import MapParseError
from fly.models import Connection, MapData, Zone, ZoneType


class MapParser:
    """Parse Fly-In map files into typed in-memory structures."""

    _VALID_ZONE_TYPES: set[str] = {
        "normal", "blocked", "restricted", "priority",
    }
    _VALID_DIRECTIVES: set[str] = {
        "nb_drones", "start_hub", "hub", "end_hub", "connection",
    }
    _VALID_ZONE_KEYS: set[str] = {"zone", "color", "max_drones"}
    _VALID_CONNECTION_KEYS: set[str] = {"max_link_capacity"}

    def parse(self, path: str | Path) -> MapData:
        """Parse a map file into a MapData object."""
        file_path = Path(path)

        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise MapParseError(
                f"Cannot read file '{file_path}': {exc}"
            ) from exc

        nb_drones: int | None = None
        zones: dict[str, Zone] = {}
        connections: list[Connection] = []
        start_zone: str | None = None
        end_zone: str | None = None
        seen_connections: set[tuple[str, str]] = set()

        for line_no, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()

            if not line or line.startswith("#"):
                continue

            directive = self._get_directive(line, line_no)

            # The subject requires nb_drones to come first. Comments and blank
            # lines are skipped above, so this is the first real directive.
            if nb_drones is None and directive != "nb_drones":
                raise MapParseError(
                    f"Line {line_no}: nb_drones must be declared before any "
                    f"other directive"
                )

            if directive == "nb_drones":
                if nb_drones is not None:
                    raise MapParseError(
                        f"Line {line_no}: duplicate nb_drones declaration"
                    )
                nb_drones = self._parse_nb_drones(line, line_no)
                continue

            if directive == "start_hub":
                if start_zone is not None:
                    raise MapParseError(
                        f"Line {line_no}: duplicate start_hub declaration"
                    )
                zone = self._parse_zone(line, line_no, is_start=True)
                self._add_zone(zone, zones, line_no)
                start_zone = zone.name
                continue

            if directive == "end_hub":
                if end_zone is not None:
                    raise MapParseError(
                        f"Line {line_no}: duplicate end_hub declaration"
                    )
                zone = self._parse_zone(line, line_no, is_end=True)
                self._add_zone(zone, zones, line_no)
                end_zone = zone.name
                continue

            if directive == "hub":
                zone = self._parse_zone(line, line_no)
                self._add_zone(zone, zones, line_no)
                continue

            connection = self._parse_connection(line, line_no)
            self._ensure_known_zones(connection, zones, line_no)

            key = self._connection_key(connection.left, connection.right)
            if key in seen_connections:
                raise MapParseError(
                    f"Line {line_no}: duplicate connection "
                    f"'{connection.left}-{connection.right}'"
                )
            seen_connections.add(key)
            connections.append(connection)

        if nb_drones is None:
            raise MapParseError("Missing nb_drones declaration")
        if start_zone is None:
            raise MapParseError("Missing start_hub declaration")
        if end_zone is None:
            raise MapParseError("Missing end_hub declaration")

        return MapData(
            nb_drones=nb_drones,
            zones=zones,
            connections=connections,
            start_zone=start_zone,
            end_zone=end_zone,
        )

    @staticmethod
    def _connection_key(left: str, right: str) -> tuple[str, str]:
        """Return a direction-independent key, so a-b matches b-a."""
        return (left, right) if left <= right else (right, left)

    def _get_directive(self, line: str, line_no: int) -> str:
        """Extract and validate the directive part of a line."""
        if ":" not in line:
            raise MapParseError(f"Line {line_no}: missing ':' separator")
        directive = line.split(":", 1)[0].strip()
        if directive not in self._VALID_DIRECTIVES:
            raise MapParseError(
                f"Line {line_no}: unknown directive '{directive}'"
            )
        return directive

    def _parse_nb_drones(self, line: str, line_no: int) -> int:
        """Parse nb_drones."""
        value = line.split(":", 1)[1].strip()
        if not value.isdigit() or int(value) <= 0:
            raise MapParseError(
                f"Line {line_no}: nb_drones must be a positive integer"
            )
        return int(value)

    def _parse_zone(
        self,
        line: str,
        line_no: int,
        *,
        is_start: bool = False,
        is_end: bool = False,
    ) -> Zone:
        """Parse a zone definition line."""
        head, meta = self._split_metadata(line, line_no)
        parts = head.split()

        # Exactly: "<directive>: <name> <x> <y>".
        if len(parts) != 4:
            raise MapParseError(
                f"Line {line_no}: invalid zone syntax, expected "
                f"'<name> <x> <y>' followed by optional [metadata]"
            )

        name = parts[1]
        self._validate_zone_name(name, line_no)
        x = self._parse_int(parts[2], line_no, "x")
        y = self._parse_int(parts[3], line_no, "y")

        metadata = self._parse_metadata(
            meta, line_no, self._VALID_ZONE_KEYS
        )

        zone_type: ZoneType = "normal"
        if "zone" in metadata:
            zone_value = metadata["zone"]
            if zone_value not in self._VALID_ZONE_TYPES:
                raise MapParseError(
                    f"Line {line_no}: invalid zone type '{zone_value}'"
                )
            zone_type = zone_value  # type: ignore[assignment]

        max_drones = 1
        if "max_drones" in metadata:
            max_drones = self._parse_positive_int(
                metadata["max_drones"], line_no, "max_drones"
            )

        # max_drones is ignored on the start and end hubs: any number of
        # drones may sit in one, so the value is validated then dropped.
        if is_start or is_end:
            max_drones = 1

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

    def _parse_connection(self, line: str, line_no: int) -> Connection:
        """Parse a connection definition."""
        head, meta = self._split_metadata(line, line_no)
        parts = head.split()

        if len(parts) != 2:
            raise MapParseError(
                f"Line {line_no}: invalid connection syntax, expected "
                f"'<zone1>-<zone2>' followed by optional [metadata]"
            )

        raw = parts[1]
        if "-" not in raw:
            raise MapParseError(f"Line {line_no}: invalid connection format")

        left, right = raw.split("-", 1)
        if not left or not right:
            raise MapParseError(
                f"Line {line_no}: invalid connection endpoints"
            )
        if left == right:
            raise MapParseError(
                f"Line {line_no}: a zone cannot connect to itself"
            )

        metadata = self._parse_metadata(
            meta, line_no, self._VALID_CONNECTION_KEYS
        )

        max_link_capacity = 1
        if "max_link_capacity" in metadata:
            max_link_capacity = self._parse_positive_int(
                metadata["max_link_capacity"], line_no, "max_link_capacity"
            )

        return Connection(
            left=left, right=right, max_link_capacity=max_link_capacity
        )

    def _split_metadata(self, line: str, line_no: int) -> tuple[str, str]:
        """Split a line into its main part and its metadata block."""
        if "[" not in line:
            if "]" in line:
                raise MapParseError(
                    f"Line {line_no}: closing bracket without an opening one"
                )
            return line, ""
        if not line.endswith("]"):
            raise MapParseError(f"Line {line_no}: missing closing bracket")

        head, _, rest = line.partition("[")
        body = rest[:-1]
        if "[" in body or "]" in body:
            raise MapParseError(
                f"Line {line_no}: malformed metadata block"
            )
        return head.strip(), body.strip()

    def _parse_metadata(
        self, meta: str, line_no: int, allowed: set[str]
    ) -> dict[str, str]:
        """Parse metadata items like key=value."""
        if not meta:
            return {}

        result: dict[str, str] = {}

        for item in meta.split():
            if "=" not in item:
                raise MapParseError(
                    f"Line {line_no}: invalid metadata token '{item}'"
                )
            key, value = item.split("=", 1)
            if not key or not value:
                raise MapParseError(
                    f"Line {line_no}: invalid metadata token '{item}'"
                )
            if key not in allowed:
                raise MapParseError(
                    f"Line {line_no}: unknown metadata key '{key}' "
                    f"(expected one of: {', '.join(sorted(allowed))})"
                )
            if key in result:
                raise MapParseError(
                    f"Line {line_no}: duplicated metadata key '{key}'"
                )
            result[key] = value

        return result

    def _parse_int(self, value: str, line_no: int, field: str) -> int:
        """Parse an integer value."""
        try:
            return int(value)
        except ValueError as exc:
            raise MapParseError(
                f"Line {line_no}: invalid {field} '{value}'"
            ) from exc

    def _parse_positive_int(
        self, value: str, line_no: int, field: str
    ) -> int:
        """Parse a positive integer value."""
        number = self._parse_int(value, line_no, field)
        if number <= 0:
            raise MapParseError(
                f"Line {line_no}: {field} must be a positive integer"
            )
        return number

    def _validate_zone_name(self, name: str, line_no: int) -> None:
        """Validate a zone name."""
        if not name:
            raise MapParseError(f"Line {line_no}: empty zone name")
        if "-" in name or " " in name:
            raise MapParseError(
                f"Line {line_no}: zone names cannot contain spaces or '-'"
            )

    def _add_zone(
        self, zone: Zone, zones: dict[str, Zone], line_no: int
    ) -> None:
        """Add a zone after checking that its name is unique."""
        if zone.name in zones:
            raise MapParseError(
                f"Line {line_no}: duplicate zone '{zone.name}'"
            )
        zones[zone.name] = zone

    def _ensure_known_zones(
        self, connection: Connection, zones: dict[str, Zone], line_no: int
    ) -> None:
        """Ensure both endpoints exist before adding a connection."""
        if connection.left not in zones:
            raise MapParseError(
                f"Line {line_no}: unknown zone '{connection.left}'"
            )
        if connection.right not in zones:
            raise MapParseError(
                f"Line {line_no}: unknown zone '{connection.right}'"
            )
