from fly.app import FlyInApp
from fly.cli import parse_args


def main() -> int:
    args = parse_args()
    app = FlyInApp(args.map)
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())