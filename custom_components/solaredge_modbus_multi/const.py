DOMAIN = "solaredge_modbus_multi"
DEFAULT_NAME = "SolarEdge"
DEFAULT_SCAN_INTERVAL = 300
DEFAULT_PORT = 1502
DEFAULT_NUMBER_INVERTERS = 1
DEFAULT_DEVICE_ID = 1
DEFAULT_DETECT_METERS = True
DEFAULT_DETECT_BATTERIES = False
DEFAULT_SINGLE_DEVICE_ENTITY = True
DEFAULT_KEEP_MODBUS_OPEN = False
CONF_NUMBER_INVERTERS = "number_of_inverters"
CONF_DEVICE_ID = "device_id"
CONF_DETECT_METERS = "detect_meters"
CONF_DETECT_BATTERIES = "detect_batteries"
CONF_SINGLE_DEVICE_ENTITY = "single_device_entity"
CONF_KEEP_MODBUS_OPEN = "keep_modbus_open"

# units missing in homeassistant core
ENERGY_VOLT_AMPERE_HOUR = "VAh"
ENERGY_VOLT_AMPERE_REACTIVE_HOUR = "varh"

SUNSPEC_NOT_IMPL_INT16 = 0x8000
SUNSPEC_NOT_IMPL_UINT16 = 0xFFFF
SUNSPEC_NOT_ACCUM_ACC16 = 0x0000
SUNSPEC_NOT_IMPL_INT32 = 0x80000000
SUNSPEC_NOT_IMPL_UINT32 = 0xFFFFFFFF
SUNSPEC_NOT_ACCUM_ACC32 = 0x00000000
SUNSPEC_ACCUM_LIMIT = 4294967295

SUNSPEC_SF_RANGE = [-10, -9, -8, -7, -6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

# parameter names per sunspec
DEVICE_STATUS_DESC = {
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
DEVICE_STATUS = {
    SUNSPEC_NOT_IMPL_INT16: None,
    0: "Unknown",
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
    SUNSPEC_NOT_IMPL_INT16: None,
    0: "No Error",
    17: "Temperature too high",
    25: "Isolation faults",
    27: "Hardware error",
    31: "AC voltage too high",
    33: "AC voltage too high",
    32: "AC voltage too low",
    34: "AC freq. too high",
    35: "AC freq. too low",
    41: "AC voltage too low",
    44: "No country selected",
    64: "AC voltage too high",
    65: "AC voltage too high",
    66: "AC voltage too high",
    61: "AC voltage too low",
    62: "AC voltage too low",
    63: "AC voltage too low",
    67: "AC voltage too low",
    68: "AC voltage too low",
    69: "AC voltage too low",
    79: "AC freq. too high",
    80: "AC freq. too high",
    81: "AC freq. too high",
    82: "AC freq. too low",
    83: "AC freq. too low",
    84: "AC freq. too low",
    95: "Hardware error",
    104: "Temperature too high",
    106: "Hardware error",
    120: "Hardware error",
    121: "Isolation faults",
    125: "Hardware error",
    126: "Hardware error",
    150: "Arc fault detected",
    151: "Arc fault detected",
    153: "Hardware error",
}

SUNSPEC_DID = {
    101: "Single Phase Inverter",
    102: "Split Phase Inverter",
    103: "Three Phase Inverter",
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
    0: "Off",
    1: "Standby",
    2: "Init",
    3: "Charge",
    4: "Discharge",
    5: "Fault",
    7: "Idle",
}
