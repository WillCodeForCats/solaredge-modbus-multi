"""Helpers for SolarEdge protocol values and device ID lists."""

from __future__ import annotations

import ipaddress
import logging
import struct

from awesomeversion import AwesomeVersion, AwesomeVersionStrategy

from .components import component_field_names
from .const import DOMAIN_REGEX
from .exceptions import DeviceListError

_LOGGER = logging.getLogger(__name__)


def float_to_hex(f: float) -> str:
    """Convert a float number to a hex string for display."""
    if not isinstance(f, (float, int)):
        raise TypeError(f"Expected float or int, got {type(f).__name__}")

    try:
        return hex(struct.unpack("<I", struct.pack("<f", float(f)))[0])
    except struct.error as e:
        raise ValueError(f"Error converting {f} to hex: {e}") from e


def host_valid(host):
    """Return True if hostname or IP address is valid."""
    try:
        return ipaddress.ip_address(host).version in (4, 6)
    except ValueError:
        return DOMAIN_REGEX.match(host)


def device_list_from_string(value: str) -> list[int]:
    """Convert a string of device IDs and ID ranges into a list of device IDs.

    The input can be a single ID or a range of IDs separated by commas.

    Args:
        value: A string that represents a list of device IDs. The device IDs
            can be specified as individual IDs or as ranges separated by a
            hyphen. For example, the string "1,3-5,7" represents the device
            IDs 1, 3, 4, 5 and 7.

    Returns:
        A sorted list of device IDs.

    Raises:
        DeviceListError: The list or one of its IDs is invalid.

    Credit: https://github.com/thargy/modbus-scanner/blob/main/scan.py
    """

    parts = [p.strip() for p in value.split(",")]
    ids = []
    for p in parts:
        r = [i.strip() for i in p.split("-")]
        if len(r) < 2:
            # We have a single id
            ids.append(check_device_id(r[0]))

        elif len(r) > 2:
            # Invalid range, multiple '-'s
            raise DeviceListError("invalid_range_format")

        else:
            # Looks like a range
            start = check_device_id(r[0])
            end = check_device_id(r[1])
            if end < start:
                raise DeviceListError("invalid_range_lte")

            ids.extend(range(start, end + 1))

    return sorted(set(ids))


def check_device_id(value: str | int) -> int:
    """Check that a value is a valid device ID between 1 and 247.

    Raises an error if it is not.

    Args:
        value: The input value being checked for validity as a device ID.

    Returns:
        The device ID as an integer.

    Raises:
        DeviceListError: The value is empty or not a valid device ID.

    Credit: https://github.com/thargy/modbus-scanner/blob/main/scan.py
    """

    if len(value) == 0:
        raise DeviceListError("empty_device_id")

    try:
        device_id = int(value)

        if (device_id < 1) or device_id > 247:
            raise DeviceListError("invalid_device_id")

    except ValueError as err:
        raise DeviceListError("invalid_device_id") from err

    return device_id


def parse_se_version(version_str: str) -> AwesomeVersion:
    """Strip zero-padding from SolarEdge firmware version strings."""
    stripped = ".".join(str(int(p)) for p in version_str.split("."))
    return AwesomeVersion(stripped, ensure_strategy=AwesomeVersionStrategy.SIMPLEVER)


def log_component_fields(prefix: str, component) -> None:
    """Debug-log every field of a just-read component on one line, by name."""
    if not _LOGGER.isEnabledFor(logging.DEBUG):
        return

    fields = []
    for name in component_field_names(component):
        value = getattr(component, name)
        if isinstance(value, float):
            display_value = float_to_hex(value)
        elif isinstance(value, int):
            display_value = hex(value)
        else:
            display_value = repr(value)
        if isinstance(value, int):
            fields.append(f"{name}={display_value}")
        else:
            fields.append(f"{name}={display_value}<{type(value).__name__}>")
    _LOGGER.debug("%s: %s", prefix, " ".join(fields))
