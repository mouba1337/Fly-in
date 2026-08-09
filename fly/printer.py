from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from fly.models import Move


class Printer:
    """Render simulation output in the terminal."""

    def __init__(self) -> None:
        self._console = Console()

    def print_banner(self) -> None:
        """Print app banner."""
        self._console.print(Panel("Fly-In", style="green"))

    def print_map(self, path: str) -> None:
        """Print loaded map path."""
        self._console.print(Panel(path, border_style="violet"))

    def print_turn(self, moves: list[Move]) -> None:
        """Print one turn of simulation output."""
        line = Text()

        for index, move in enumerate(moves):
            if index > 0:
                line.append(" ")

            line.append(f"D{move.drone_id}", style=self._drone_style(move.drone_id))
            line.append("-", style="white")

            if move.is_transit and move.connection_name:
                line.append(move.connection_name, style="yellow")
            else:
                line.append(move.destination, style=self._destination_style(move.destination_type))

        self._console.print(line, soft_wrap=True, crop=False)

    def print_error(self, message: str) -> None:
        """Print an error panel."""
        self._console.print(Panel(message, title="ERROR", border_style="red"))

    def _drone_style(self, drone_id: int) -> str:
        """Return a stable color for each drone."""
        palette = ["cyan", "magenta", "blue", "green", "yellow", "red"]
        return palette[(drone_id - 1) % len(palette)]

    def _destination_style(self, zone_type: str) -> str:
        """Return a style for the zone type."""
        if zone_type == "blocked":
            return "grey50"
        if zone_type == "restricted":
            return "red"
        if zone_type == "priority":
            return "blue"
        return "green"