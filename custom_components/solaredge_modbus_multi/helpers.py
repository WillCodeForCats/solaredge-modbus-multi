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


def deviceIdsFromString(value: str) -> list[int]:
    """The function `deviceIdsFromString` takes a string input and returns a list of
    device IDs, where the input can be a single ID or a range of IDs separated by commas

    Parameters
    ----------
    value
        The `value` parameter is a string that represents a list of device IDs. The
        device IDs can be specified as individual IDs or as ranges separated by a hyphen
        For example, the string "1,3-5,7" represents the device IDs 1, 3, 4, 5 and 7

    Returns
    -------
        The function `checkDeviceIds` returns a list of device IDs.

    Credit: https://github.com/thargy/modbus-scanner/blob/main/scan.py
    """
    parts = [p.strip() for p in value.split(",")]
    ids = []
    for p in parts:
        r = [i.strip() for i in p.split("-")]
        if len(r) < 2:
            # We have a single id
            ids.append(checkDeviceId(r[0]))

        elif len(r) > 2:
            # Invalid range, multiple '-'s
            raise HomeAssistantError(
                f"'{p}' in '{value}' looks like a range but has multiple '-'s."
            )

        else:
            # Looks like a range
            start = checkDeviceId(r[0])
            end = checkDeviceId(r[1])
            if end < start:
                raise HomeAssistantError(
                    f"'{start}' must be less than or equal to {end}."
                )

            ids.extend(range(start, end + 1))

    return sorted(set(ids))


def checkDeviceId(value: (str | int)) -> int:
    """The `checkDeviceId` function takes a value and checks if it is a valid device
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
    id = int(value)

    if (id < 1) or id > 247:
        raise HomeAssistantError(f"'{value}' must be a device ID between 1 and 247")

    return id
