"""The SolarEdge Modbus Multi helpers module."""

from __future__ import annotations


def safe_version_tuple(version_str: str) -> tuple[int, ...]:
    """Parse a dotted version string like '4.10.0' into a comparable tuple."""
    try:
        return tuple(int(part) for part in version_str.split("."))
    except ValueError as err:
        raise ValueError(f"Invalid version string: {version_str}") from err
