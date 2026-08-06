from __future__ import annotations

from collections.abc import Iterator

from fly.models import MapData, Move


class Simulator:
    """Turn-by-turn drone scheduler."""

    def run(self, data: MapData) -> Iterator[list[Move]]:
        """Yield one simulation turn at a time."""
        yield from ()