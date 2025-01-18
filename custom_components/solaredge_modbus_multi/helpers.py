from __future__ import annotations

import ipaddress
import struct

from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN_REGEX


def float_to_hex(f):
    try:
        return hex(struct.unpack("<I", struct.pack("<f", f))[0])
    except struct.error as e:
        raise TypeError(e)


def parse_modbus_string(s: str) -> str:
    s = s.decode(encoding="utf-8", errors="ignore")
    s = s.replace("\x00", "").rstrip()
    return str(s)


def update_accum(self, accum_value: int) -> None:
    if self.last is None:
        self.last = 0

    if not accum_value > 0:
        raise ValueError("update_accum must be non-zero value.")

    if accum_value >= self.last:
        # doesn't check accumulator rollover, but it would probably take
        # several decades to roll over to 0 so we'll worry about it later
        self.last = accum_value
        return accum_value
    else:
        raise ValueError("update_accum must be an increasing value.")


def host_valid(host):
    """Return True if hostname or IP address is valid."""
    try:
        if ipaddress.ip_address(host).version == (4 or 6):
            return True

    except ValueError:
        return DOMAIN_REGEX.match(host)


def device_list_from_string(value: str) -> list[int]:
    """The function `device_list_from_string` takes a string input and returns a list of
    device IDs, where the input can be a single ID or a range of IDs separated by commas

    Parameters
    ----------
    value
        The `value` parameter is a string that represents a list of device IDs. The
        device IDs can be specified as individual IDs or as ranges separated by a hyphen
        For example, the string "1,3-5,7" represents the device IDs 1, 3, 4, 5 and 7

    Returns
    -------
        The function `device_list_from_string` returns a list of device IDs.

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
    """The `check_device_id` function takes a value and checks if it is a valid device
    ID between 1 and 247, raising an error if it is not.

    Parameters
    ----------
    value
        The value parameter is the input value that is
        being checked for validity as a device ID.

    Returns
    -------
        the device ID as an integer.

    Credit: https://github.com/thargy/modbus-scanner/blob/main/scan.py
    """

    if len(value) == 0:
        raise HomeAssistantError("empty_device_id")

    try:
        id = int(value)

        if (id < 1) or id > 247:
            raise HomeAssistantError("invalid_device_id")

    except ValueError:
        raise HomeAssistantError("invalid_device_id")

    return id
