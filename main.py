"""Entry point for the Fly-In drone routing simulation."""

from __future__ import annotations

from fly.app import FlyInApp
from fly.cli import parse_args


def main() -> int:
    """Parse the command line and run the simulation."""
    args = parse_args()
    app = FlyInApp(args.map)
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
