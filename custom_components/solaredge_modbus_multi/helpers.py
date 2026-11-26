"""The SolarEdge Modbus Multi helpers module."""

from __future__ import annotations

from typing import Any

from .const import ATTR_STATUS_TEXT, ATTR_STATUS_VALUE
from .lib.const import VENDOR4_STATUS, VENDOR_STATUS, SunSpecNotImpl


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


def safe_version_tuple(version_str: str) -> tuple[int, ...]:
    """Parse a dotted version string like '4.10.0' into a comparable tuple."""
    try:
        return tuple(int(part) for part in version_str.split("."))
    except ValueError as err:
        raise ValueError(f"Invalid version string: {version_str}") from err
