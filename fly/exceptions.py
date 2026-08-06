class FlyInError(Exception):
    """Base exception for Fly-In."""


class MapParseError(FlyInError):
    """Raised when the map file is invalid."""


class SimulationError(FlyInError):
    """Raised when the simulation fails."""


class CliError(FlyInError):
    """Raised when CLI input is invalid."""