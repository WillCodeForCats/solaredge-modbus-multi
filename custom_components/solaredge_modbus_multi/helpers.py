def scale_factor(value: int, sf: int):
    try:
        return value * (10 ** sf)
    except ZeroDivisionError:
        return 0
    
def watts_to_kilowatts(value):
    return round(value * 0.001, 3)

def parse_modbus_string(s: str) -> str:
    return s.decode(encoding="utf-8", errors="ignore").replace("\x00", "").rstrip()

def update_accum(self, raw: int, current: int) -> None:
    
    if self.last is None:
        self.last = 0
        
    if not raw > 0:
        raise ValueError(f"update_accum must be non-zero value.")
            
    if current >= self.last:
        # doesn't account for accumulator rollover, but it would probably take
        # several decades to roll over to 0 so we'll worry about it later
        self.last = current
        return current    
    else:
        raise ValueError(f"update_accum must be an increasing value.")
