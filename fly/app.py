"""Application wiring: parse a map, run it, render the result."""

from __future__ import annotations

from fly.exceptions import FlyInError
from fly.parser import MapParser
from fly.printer import Printer
from fly.simulator import Simulator


class FlyInApp:
    """Run one simulation end to end: parse, schedule, then render."""

    def __init__(self, map_path: str) -> None:
        """Store the map path and build the parser, printer and simulator.

        Args:
            map_path: Path to the map file to simulate.
        """
        self._map_path = map_path
        self._parser = MapParser()
        self._printer = Printer()
        self._simulator = Simulator()

    def run(self) -> int:
        """Run the simulation and report the process exit code.

        Returns:
            0 when every drone reached the end hub, 1 on any error.
        """
        try:
            data = self._parser.parse(self._map_path)
            self._printer.load_zones(data.zones)
            self._printer.print_banner()
            self._printer.print_map(self._map_path)

            for turn in self._simulator.run(data):
                self._printer.print_turn(turn)
            return 0
        except FlyInError as exc:
            self._printer.print_error(str(exc))
            return 1
        except Exception as exc:
            self._printer.print_error(f"Unexpected error: {exc}")
            return 1
