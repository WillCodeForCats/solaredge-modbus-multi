from __future__ import annotations

import ipaddress
import struct

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
