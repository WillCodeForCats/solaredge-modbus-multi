import struct


def scale_factor(value: int, sf: int):
    try:
        return value * (10 ** sf)
    except ZeroDivisionError:
        return 0


def watts_to_kilowatts(value):
    return round(value * 0.001, 3)


def float_to_hex(f):
    return hex(struct.unpack("<I", struct.pack("<f", f))[0])


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
