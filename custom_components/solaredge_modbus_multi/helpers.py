def scale_factor(self, value: int, sf: int):
    try:
        return value * (10 ** sf)
    except ZeroDivisionError:
        return 0
    
def watts_to_kilowatts(self, value):
    return round(value * 0.001, 3)

def parse_modbus_string(self, s: str) -> str:
    return s.decode(encoding="utf-8", errors="ignore").replace("\x00", "").rstrip()

def update_accum(self, key: str, raw: int, current: int) -> None:
    try:
        last = self.data[key]
    except KeyError:
        last = 0
        
    if last is None:
        last = 0

    if not raw > 0:
        raise ValueError(f"update_accum {key} must be non-zero value.")
            
    if current >= last:
        # doesn't account for accumulator rollover, but it would probably take
        # several decades to roll over to 0 so we'll worry about it later
        self.data[key] = current    
    else:
        raise ValueError(f"update_accum {key} must be an increasing value.")
