from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from fly.models import Move


class Printer:
    def __init__(self) -> None:
        self._console = Console()

    def print_banner(self) -> None:
        self._console.print(Panel("Fly-In", style="green"))

    def print_map(self, path: str) -> None:
        self._console.print(Panel(path, border_style="violet"))

    def print_turn(self, moves: list[Move]) -> None:
        line = Text()
        for index, move in enumerate(moves):
            if index > 0:
                line.append(" ")
            line.append(f"D{move.drone_id}", style="cyan")
            line.append("-", style="white")
            line.append(move.destination, style="yellow" if move.is_transit else "green")
        self._console.print(line)

    def print_error(self, message: str) -> None:
        self._console.print(Panel(message, title="ERROR", border_style="red"))