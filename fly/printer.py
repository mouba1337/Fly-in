from __future__ import annotations

from rich.color import Color, ColorParseError
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from fly.models import Move, Zone


class Printer:
    """Render simulation output in the terminal."""

    # The subject allows any single-word string as a colour, but rich only
    # understands its own palette. These CSS names are common in map files and
    # map cleanly onto hex codes, which rich always accepts.
    _COLOR_ALIASES: dict[str, str] = {
        "orange": "#ffa500",
        "brown": "#a52a2a",
        "crimson": "#dc143c",
        "darkred": "#8b0000",
        "gold": "#ffd700",
        "lime": "#00ff00",
        "maroon": "#800000",
        "silver": "#c0c0c0",
        "navy": "#000080",
        "olive": "#808000",
        "teal": "#008080",
        "pink": "#ffc0cb",
        "indigo": "#4b0082",
    }

    _TYPE_STYLES: dict[str, str] = {
        "blocked": "grey50",
        "restricted": "red",
        "priority": "blue",
        "normal": "green",
    }

    _DRONE_PALETTE: list[str] = [
        "cyan",
        "magenta",
        "blue",
        "green",
        "yellow",
        "red",
    ]

    def __init__(self) -> None:
        self._console = Console()
        self._zone_styles: dict[str, str] = {}

    def load_zones(self, zones: dict[str, Zone]) -> None:
        """Resolve each zone's display style once, before the simulation.

        Colours declared in the map win; a colour rich cannot render falls
        back to the zone-type style so an exotic value never crashes the run.
        """
        self._zone_styles = {}

        for name, zone in zones.items():
            style = self._resolve_color(zone.color)
            if style is None:
                style = self._TYPE_STYLES[zone.zone_type]
            self._zone_styles[name] = style

    def print_banner(self) -> None:
        """Print app banner."""
        self._console.print(Panel("Fly-In", style="green"))

    def print_map(self, path: str) -> None:
        """Print loaded map path."""
        self._console.print(Panel(path, border_style="violet"))

    def print_turn(self, moves: list[Move]) -> None:
        """Print one turn of simulation output.

        A turn in which every drone waits is printed as an empty line, so the
        number of lines always matches the number of simulation turns.
        """
        line = Text()

        for index, move in enumerate(moves):
            if index > 0:
                line.append(" ")

            line.append(f"D{move.drone_id}", style=self._drone_style(move.drone_id))
            line.append("-", style="white")

            if move.is_transit and move.connection_name:
                line.append(move.connection_name, style="yellow")
            else:
                line.append(move.destination, style=self._zone_style(move))

        self._console.print(line, soft_wrap=True, crop=False)

    def print_error(self, message: str) -> None:
        """Print an error panel."""
        self._console.print(Panel(message, title="ERROR", border_style="red"))

    def _drone_style(self, drone_id: int) -> str:
        """Return a stable color for each drone."""
        return self._DRONE_PALETTE[(drone_id - 1) % len(self._DRONE_PALETTE)]

    def _zone_style(self, move: Move) -> str:
        """Return the style to use for a move's destination zone."""
        style = self._zone_styles.get(move.destination)
        if style is not None:
            return style
        return self._TYPE_STYLES.get(move.destination_type, "white")

    def _resolve_color(self, color: str | None) -> str | None:
        """Turn a map colour into something rich can render, or None."""
        if not color:
            return None

        candidate = self._COLOR_ALIASES.get(color.lower(), color)
        try:
            Color.parse(candidate)
        except ColorParseError:
            return None
        return candidate
