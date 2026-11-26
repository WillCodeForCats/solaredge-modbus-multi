"""The SolarEdge Modbus Multi helpers module."""

from __future__ import annotations

import ipaddress
import struct
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from modbus_connection import ModbusTcpParams

try:
    # Not in the modbus integration's __all__, so core may move it. Without
    # it we simply cannot tell who shares a connection.
    from homeassistant.components.modbus.connection import async_get_connection_info
except ImportError:  # pragma: no cover
    async_get_connection_info = None

from .const import (
    ATTR_STATUS_TEXT,
    ATTR_STATUS_VALUE,
    DOMAIN,
    DOMAIN_REGEX,
    METER_EVENTS,
    METER_EVENTS_TEXT,
    SUNSPEC_SF_RANGE,
    VENDOR4_STATUS,
    VENDOR_STATUS,
    ConfName,
    ConnectionMode,
    SunSpecNotImpl,
)


def float_to_hex(f: float) -> str:
    """Convert a float number to a hex string for display."""
    if not isinstance(f, (float, int)):
        raise TypeError(f"Expected float or int, got {type(f).__name__}")

    try:
        return hex(struct.unpack("<I", struct.pack("<f", float(f)))[0])
    except struct.error as e:
        raise ValueError(f"Error converting {f} to hex: {e}") from e


def other_modbus_holders(hass: HomeAssistant, host: str, port: int) -> set[str]:
    """Return the domains of other integrations sharing a Modbus/TCP connection.

    The modbus integration lists the config entries holding units on each
    device but not the link's timeout, so another holder is the closest sign
    that a long timeout may be forced on the connection. Our own integration
    is not counted.
    """
    if async_get_connection_info is None:
        return set()

    endpoint = ModbusTcpParams(host=host, port=port).endpoint
    domains = set()
    for info in async_get_connection_info(hass):
        if info.endpoint != endpoint:
            continue
        for entry_id in info.units:
            entry = hass.config_entries.async_get_entry(entry_id)
            if entry is not None and entry.domain != DOMAIN:
                domains.add(entry.domain)
    return domains


def modbus_connection_exists(hass: HomeAssistant, host: str, port: int) -> bool:
    """Return True if the modbus integration already has a connection open.

    A timeout asked for on a connection we did not open replaces the one any
    other holder of the same device ID asked for. Assumes there is one when
    the modbus integration cannot tell us.
    """
    if async_get_connection_info is None:
        return True

    endpoint = ModbusTcpParams(host=host, port=port).endpoint
    return any(info.endpoint == endpoint for info in async_get_connection_info(hass))


def scale_sunspec_int16(value, sf) -> float | None:
    """Return an int16 SunSpec value with its scale factor applied.

    Returns None if the value or scale factor is missing, not implemented,
    or the scale factor is out of range. The not implemented value 0x8000 is
    checked both as read (32768) and as decoded to a signed int16 (-32768).
    """
    if (
        value is None
        or value in (SunSpecNotImpl.INT16, -SunSpecNotImpl.INT16)
        or sf is None
        or sf == SunSpecNotImpl.INT16
        or sf not in SUNSPEC_SF_RANGE
    ):
        return None
    return value * (10**sf)


def default_virtual_system(device_list: list) -> bool:
    """Return the default for the virtual system option.

    Return true when the hub has more than one inverter.
    """
    return len(device_list) > 1


def inverter_vendor_status(data, use_status_vendor4: bool) -> dict[str, Any]:
    """Return the vendor status value and its text, when known."""
    attrs: dict[str, Any] = {}

    if use_status_vendor4:
        value = data.I_Status_Vendor4
        if value is not None and value != SunSpecNotImpl.UINT32:
            controller = (value >> 24) & 0xFF
            error = value & 0xFFFF
            attrs[ATTR_STATUS_VALUE] = f"{controller:X}x{error:X}"
            if controller in VENDOR4_STATUS and error in VENDOR4_STATUS[controller]:
                attrs[ATTR_STATUS_TEXT] = VENDOR4_STATUS[controller][error]
    else:
        value = data.I_Status_Vendor
        if value is not None and value != SunSpecNotImpl.UINT16:
            attrs[ATTR_STATUS_VALUE] = value
            if value in VENDOR_STATUS:
                attrs[ATTR_STATUS_TEXT] = VENDOR_STATUS[value]

    return attrs


def meter_event_names(value: int) -> list[str]:
    """Return the names of the meter event bits set in value."""
    return [name for bit, name in METER_EVENTS.items() if value & (1 << bit)]


def meter_event_texts(value: int) -> list[str]:
    """Return the descriptions of the meter event bits set in value.

    Bits without a description (reserved and OEM) use their name.
    """
    return [
        METER_EVENTS_TEXT.get(bit, name)
        for bit, name in METER_EVENTS.items()
        if value & (1 << bit)
    ]


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
            raise HomeAssistantError("invalid_range_format")

        else:
            # Looks like a range
            start = check_device_id(r[0])
            end = check_device_id(r[1])
            if end < start:
                raise HomeAssistantError("invalid_range_lte")

            ids.extend(range(start, end + 1))

    return sorted(set(ids))


def check_device_id(value: str | int) -> int:
    """Check that a value is a valid device ID between 1 and 247.

    Raises an error if it is not.

    Args:
        value: The input value being checked for validity as a device ID.

    Returns:
        The device ID as an integer.

    Credit: https://github.com/thargy/modbus-scanner/blob/main/scan.py
    """

    if len(value) == 0:
        raise HomeAssistantError("empty_device_id")

    try:
        device_id = int(value)

        if (device_id < 1) or device_id > 247:
            raise HomeAssistantError("invalid_device_id")

    except ValueError as err:
        raise HomeAssistantError("invalid_device_id") from err

    return device_id


def get_connection_mode(options) -> ConnectionMode:
    """Return how to connect to the inverter.

    The option in the hub configuration decides.
    """
    try:
        return ConnectionMode(options.get(ConfName.CONNECTION_MODE))
    except ValueError:
        return ConnectionMode.SHARED
