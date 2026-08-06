from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(slots=True)
class Args:
    map: str


def parse_args() -> Args:
    parser = argparse.ArgumentParser(prog="flyin")
    parser.add_argument("--map", required=True, help="Path to the map file")
    namespace = parser.parse_args()
    return Args(map=namespace.map)