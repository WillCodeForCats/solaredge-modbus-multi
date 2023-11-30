"""Constants used by SolarEdge Modbus Multi components."""
from __future__ import annotations

import re
import sys
from enum import IntEnum
from typing import Final

if sys.version_info.minor >= 11:
    # Needs Python 3.11
    from enum import StrEnum
else:
    try:
        from homeassistant.backports.enum import StrEnum

    except ImportError:
        from enum import Enum

        class StrEnum(str, Enum):
            pass


DOMAIN = "solaredge_modbus_multi"
DEFAULT_NAME = "SolarEdge"

# units missing in homeassistant core
ENERGY_VOLT_AMPERE_HOUR: Final = "VAh"
ENERGY_VOLT_AMPERE_REACTIVE_HOUR: Final = "varh"

# from voluptuous/validators.py
DOMAIN_REGEX = re.compile(
    # start anchor, because fullmatch is not available in python 2.7
    "(?:"
    # domain
    r"(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+"
    r"(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?$)"
    # end anchor, because fullmatch is not available in python 2.7
    r")\Z",
    re.IGNORECASE,
)


class RetrySettings(IntEnum):
    """Retry settings when opening a connection to the inverter fails."""

    Time = 800  # first attempt in milliseconds
    Ratio = 3  # time multiplier between each attempt
    Limit = 5  # number of attempts before failing


class ModbusDefaults(IntEnum):
    """Values to pass to pymodbus"""

    """
        ReconnectDelay doubles automatically with each unsuccessful connect, from
        ReconnectDelay to ReconnectDelayMax.
        Set `ReconnectDelay = 0` to avoid automatic reconnection.
        Disabled because it didn't work properly with HA Async in PR#360.
    """

    Timeout = 3  # Timeout for a request, in seconds.
    ReconnectDelay = 0  # Minimum in seconds.milliseconds before reconnecting.
    ReconnectDelayMax = 3.0  # Maximum in seconds.milliseconds before reconnecting.


class SolarEdgeTimeouts(IntEnum):
    """Timeouts in milliseconds."""

    Inverter = 8400
    Device = 1200
    Init = 1200


class BatteryLimit(IntEnum):
    """Configure battery limits for input and display validation."""

    Vmin = 0  # volts
    Vmax = 1000  # volts
    Amin = -200  # amps
    Amax = 200  # amps
    Tmax = 100  # degrees C
    Tmin = -30  # degrees C
    ChargeMax = 1000000  # watts
    DischargeMax = 1000000  # watts


class ConfDefaultInt(IntEnum):
    """Defaults for options that are integers."""

    SCAN_INTERVAL = 300
    PORT = 1502
    NUMBER_INVERTERS = 1
    DEVICE_ID = 1
    SLEEP_AFTER_WRITE = 0
    BATTERY_RATING_ADJUST = 0
    BATTERY_ENERGY_RESET_CYCLES = 0


class ConfDefaultFlag(IntEnum):
    """Defaults for options that are booleans."""

    DETECT_METERS = 1
    DETECT_BATTERIES = 0
    DETECT_EXTRAS = 1
    KEEP_MODBUS_OPEN = 0
    ADV_PWR_CONTROL = 0
    ADV_STORAGE_CONTROL = 0
    ADV_SITE_LIMIT_CONTROL = 0
    ALLOW_BATTERY_ENERGY_RESET = 0


class ConfName(StrEnum):
    NUMBER_INVERTERS = "number_of_inverters"
    DEVICE_ID = "device_id"
    DETECT_METERS = "detect_meters"
    DETECT_BATTERIES = "detect_batteries"
    DETECT_EXTRAS = "detect_extras"
    KEEP_MODBUS_OPEN = "keep_modbus_open"
    ADV_PWR_CONTROL = "advanced_power_control"
    ADV_STORAGE_CONTROL = "adv_storage_control"
    ADV_SITE_LIMIT_CONTROL = "adv_site_limit_control"
    ALLOW_BATTERY_ENERGY_RESET = "allow_battery_energy_reset"
    SLEEP_AFTER_WRITE = "sleep_after_write"
    BATTERY_RATING_ADJUST = "battery_rating_adjust"
    BATTERY_ENERGY_RESET_CYCLES = "battery_energy_reset_cycles"


class SunSpecAccum(IntEnum):
    NA16 = 0x0000
    NA32 = 0x00000000
    LIMIT16 = 0xFFFF
    LIMIT32 = 0xFFFFFFFF


class SunSpecNotImpl(IntEnum):
    INT16 = 0x8000
    UINT16 = 0xFFFF
    INT32 = 0x80000000
    UINT32 = 0xFFFFFFFF
    FLOAT32 = 0x7FC00000


SUNSPEC_SF_RANGE = [
    -10,
    -9,
    -8,
    -7,
    -6,
    -5,
    -4,
    -3,
    -2,
    -1,
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
]

# parameter names per sunspec
DEVICE_STATUS = {
    1: "I_STATUS_OFF",
    2: "I_STATUS_SLEEPING",
    3: "I_STATUS_STARTING",
    4: "I_STATUS_MPPT",
    5: "I_STATUS_THROTTLED",
    6: "I_STATUS_SHUTTING_DOWN",
    7: "I_STATUS_FAULT",
    8: "I_STATUS_STANDBY",
}

# English descriptions of parameter names
DEVICE_STATUS_TEXT = {
    1: "Off",
    2: "Sleeping (Auto-Shutdown)",
    3: "Grid Monitoring",
    4: "Production",
    5: "Production (Curtailed)",
    6: "Shutting Down",
    7: "Fault",
    8: "Maintenance",
}

VENDOR_STATUS = {
    SunSpecNotImpl.INT16: None,
    0: "No Error",
    17: "Temperature Too High",
    25: "Isolation Faults",
    27: "Hardware Error",
    31: "AC Voltage Too High",
    33: "AC Voltage Too High",
    32: "AC Voltage Too Low",
    34: "AC Frequency Too High",
    35: "AC Frequency Too Low",
    41: "AC Voltage Too Low",
    44: "No Country Selected",
    61: "AC Voltage Too Low",
    62: "AC Voltage Too Low",
    63: "AC Voltage Too Low",
    64: "AC Voltage Too High",
    65: "AC Voltage Too High",
    66: "AC Voltage Too High",
    67: "AC Voltage Too Low",
    68: "AC Voltage Too Low",
    69: "AC Voltage Too Low",
    79: "AC Frequency Too High",
    80: "AC Frequency Too High",
    81: "AC Frequency Too High",
    82: "AC Frequency Too Low",
    83: "AC Frequency Too Low",
    84: "AC Frequency Too Low",
    95: "Hardware Error",
    97: "Vin Buck Max",
    104: "Temperature Too High",
    106: "Hardware Error",
    107: "Battery Communication Error",
    110: "Meter Communication Error",
    120: "Hardware Error",
    121: "Isolation Faults",
    125: "Hardware Error",
    126: "Hardware Error",
    150: "Arc Fault Detected",
    151: "Arc Fault Detected",
    153: "Hardware Error",
    256: "Arc Detected",
}

SUNSPEC_DID = {
    101: "Single Phase Inverter",
    102: "Split Phase Inverter",
    103: "Three Phase Inverter",
    160: "Multiple MPPT Inverter Extension",
    201: "Single Phase Meter",
    202: "Split Phase Meter",
    203: "Three Phase Wye Meter",
    204: "Three Phase Delta Meter",
}

METER_EVENTS = {
    2: "M_EVENT_Power_Failure",
    3: "M_EVENT_Under_Voltage",
    4: "M_EVENT_Low_PF",
    5: "M_EVENT_Over_Current",
    6: "M_EVENT_Over_Voltage",
    7: "M_EVENT_Missing_Sensor",
    8: "M_EVENT_Reserved1",
    9: "M_EVENT_Reserved2",
    10: "M_EVENT_Reserved3",
    11: "M_EVENT_Reserved4",
    12: "M_EVENT_Reserved5",
    13: "M_EVENT_Reserved6",
    14: "M_EVENT_Reserved7",
    15: "M_EVENT_Reserved8",
    16: "M_EVENT_OEM1",
    17: "M_EVENT_OEM2",
    18: "M_EVENT_OEM3",
    19: "M_EVENT_OEM4",
    20: "M_EVENT_OEM5",
    21: "M_EVENT_OEM6",
    22: "M_EVENT_OEM7",
    23: "M_EVENT_OEM8",
    24: "M_EVENT_OEM9",
    25: "M_EVENT_OEM10",
    26: "M_EVENT_OEM11",
    27: "M_EVENT_OEM12",
    28: "M_EVENT_OEM13",
    29: "M_EVENT_OEM14",
    30: "M_EVENT_OEM15",
}

BATTERY_STATUS = {
    0: "B_STATUS_OFF",
    1: "B_STATUS_STANDBY",
    2: "B_STATUS_INIT",
    3: "B_STATUS_CHARGE",
    4: "B_STATUS_DISCHARGE",
    5: "B_STATUS_FAULT",
    6: "B_STATUS_PRESERVE_CHARGE",
    7: "B_STATUS_IDLE",
    10: "B_STATUS_POWER_SAVING",
}

BATTERY_STATUS_TEXT = {
    0: "Off",
    1: "Standby",
    2: "Initializing",
    3: "Charge",
    4: "Discharge",
    5: "Fault",
    6: "Preserve Charge",
    7: "Idle",
    10: "Power Saving",
}

RRCR_STATUS = {
    3: "L1",
    2: "L2",
    1: "L3",
    0: "L4",
}

MMPPT_EVENTS = {
    0: "GROUND_FAULT",
    1: "INPUT_OVER_VOLTAGE",
    3: "DC_DISCONNECT",
    5: "CABINET_OPEN",
    6: "MANUAL_SHUTDOWN",
    7: "OVER_TEMP",
    12: "BLOWN_FUSE",
    13: "UNDER_TEMP",
    14: "MEMORY_LOSS",
    15: "ARC_DETECTION",
    19: "RESERVED",
    20: "TEST_FAILED",
    21: "INPUT_UNDER_VOLTAGE",
    22: "INPUT_OVER_CURRENT",
}

STORAGE_CONTROL_MODE = {
    0: "Disabled",
    1: "Maximize Self Consumption",
    2: "Time of Use",
    3: "Backup Only",
    4: "Remote Control",
}

STORAGE_AC_CHARGE_POLICY = {
    0: "Disabled",
    1: "Always Allowed",
    2: "Fixed Energy Limit",
    3: "Percent of Production",
}

STORAGE_MODE = {
    0: "Solar Power Only (Off)",
    1: "Charge from Clipped Solar Power",
    2: "Charge from Solar Power",
    3: "Charge from Solar Power and Grid",
    4: "Discharge to Maximize Export",
    5: "Discharge to Minimize Import",
    7: "Maximize Self Consumption",
}

LIMIT_CONTROL_MODE = {
    None: "Disabled",
    0: "Export Control (Export/Import Meter)",
    1: "Export Control (Consumption Meter)",
    2: "Production Control",
}

LIMIT_CONTROL = {0: "Total", 1: "Per Phase"}
