from __future__ import annotations

import ipaddress
import struct

from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN_REGEX


def float_to_hex(f: float) -> str:
    """Convert a float number to a hex string for display."""
    if not isinstance(f, (float, int)):
        raise TypeError(f"Expected float or int, got {type(f).__name__}")

    try:
        return hex(struct.unpack("<I", struct.pack("<f", float(f)))[0])
    except struct.error as e:
        raise ValueError(f"Error converting {f} to hex: {e}")


def int_list_to_string(int_list: list[int]) -> str:
    """Convert a list of 16-bit unsigned integers into a string. Each int is 2 bytes.

    This method exists because pymodbus ModbusClientMixin.convert_from_registers with
    data_type=DATATYPE.STRING needs errors="ignore" added to handle SolarEdge strings.

    Ref: https://github.com/pymodbus-dev/pymodbus/blob/
    7fc8d3e02d9d9011c25c80149eb88318e7f50d0e/pymodbus/client/mixin.py#L719
    """
    byte_data = b"".join(i.to_bytes(2, "big") for i in int_list)
    return byte_data.decode("utf-8", errors="ignore").replace("\x00", "").rstrip()


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
