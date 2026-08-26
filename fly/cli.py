from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(slots=True)
class Args:
    """Validated command-line arguments."""

    map: str


def parse_args(argv: list[str] | None = None) -> Args:
    """Parse the command line.

    Args:
        argv: Argument list to parse. Defaults to sys.argv[1:].

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        prog="flyin",
        description="Route a fleet of drones through a network of zones.",
    )
    parser.add_argument(
        "--map",
        required=True,
        help="Path to the map file",
    )

    namespace = parser.parse_args(argv)

    return Args(map=namespace.map)
