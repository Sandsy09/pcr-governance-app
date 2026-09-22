"""Internal Python application for PCR management."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pcr-governance-app")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = ["__version__"]
